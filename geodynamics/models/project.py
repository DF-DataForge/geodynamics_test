# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api

from . import gdhandler
from .gdhandler import GeodynamicsHandler
from datetime import datetime, timedelta
import logging  # added
import re  # added
import pytz

_logger = logging.getLogger(__name__)  # added

class Project(models.Model):
    _inherit = 'project.project'

    df_gd_planning_enabled = fields.Boolean(compute='_compute_gd_planning_enabled')

    @api.depends_context('uid')
    def _compute_gd_planning_enabled(self):
        enabled = self.env['ir.config_parameter'].sudo().get_param('geodynamics.planning_project', 'True').lower() in ('true', '1', 'yes')
        for rec in self:
            rec.df_gd_planning_enabled = enabled

    df_gd_employee_ids = fields.Many2many('hr.employee', string='Werknemers Geodynamics', domain=[('df_geodynamics_id','!=',False)])
    df_gd_clocking_ids = fields.One2many(
        'geodynamics.clocking',
        'project_id',
        string='Geodynamics Clockings',
        readonly=True,
    )
    df_gd_planning_ids = fields.One2many(
        'df.geodynamics.planning',
        'project_id',
        string='Geodynamics Plannings',
        readonly=True,
    )

    df_gd_name = fields.Char(string='Geodynamics name', compute='_compute_gd_name')

    @api.depends('name')
    def _compute_gd_name(self):
        for record in self:
            # Project key: "<name>-P<id>". The 'P' prefix distinguishes a project
            # key from a task key ("<name>-<id>") in Geodynamics.
            if record.name:
                record.df_gd_name = '%s-P%s' % (record.name, record.id)
            else:
                record.df_gd_name = 'P%s' % record.id

    def _get_geodynamic_configs(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')
        return company, login, password

    def _compute_geodynamics_clocking_range(self):
        """Return (start_date, end_date) for clocking fetch following rules:
        start_date:
            project.date_start OR project.create_date (date part) OR today
        end_date:
            project.date OR max(task.date_deadline, task.create_date) across tasks
            OR project.create_date (date part) OR start_date
        Guarantees: returns date objects, end_date >= start_date.
        """
        self.ensure_one()
        # Start date logic
        if self.date_start:
            start_date = self.date_start if not isinstance(self.date_start, datetime) else self.date_start.date()
        else:
            if self.create_date:
                start_date = self.create_date.date()
            else:
                start_date = fields.Date.context_today(self)
        # End date logic
        if self.date:
            end_date = self.date if not isinstance(self.date, datetime) else self.date.date()
        else:
            tasks = self.env['project.task'].search([('project_id', '=', self.id)])
            candidate_dates = []
            for td in tasks.mapped('date_deadline'):
                if td:
                    candidate_dates.append(td if not isinstance(td, datetime) else td.date())
            for cd in tasks.mapped('create_date'):
                if cd:
                    candidate_dates.append(cd.date())
            if candidate_dates:
                end_date = max(candidate_dates)
            else:
                if self.create_date:
                    end_date = self.create_date.date()
                else:
                    end_date = start_date
        # Normalize & order
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            end_date = end_date.date()
        if end_date < start_date:
            end_date = start_date
        _logger.debug("[Geodynamics] Project %s (%s) clocking range computed: %s -> %s", self.id, self.display_name, start_date, end_date)
        return start_date, end_date

    def _extract_project_job_codes(self):
        """Extract possible job code tokens from project name.
        Current rule: codes like 'S' followed by digits (e.g. S01117) that appear in name.
        Returns set of uppercase codes.
        """
        self.ensure_one()
        name = (self.name or '').upper()
        # simple pattern: S + 5 digits (adjust if length differs)
        codes = set(re.findall(r'S\d{5}', name))
        return codes

    def _normalize_job_number_token(self, raw):
        if not raw:
            return None
        # Take prefix before ' - '
        token = raw.split(' - ')[0].strip().upper()
        # Only accept pattern S + digits
        m = re.match(r'^(S\d+)$', token)
        return m.group(1) if m else None

    def _collect_task_employees(self):
        """Collect unique hr.employee records from all tasks of this project via task.df_employee_ids."""
        self.ensure_one()
        tasks = self.env['project.task'].search([('project_id', '=', self.id)])
        emps = tasks.mapped('df_employee_ids')
        _logger.debug('[Geodynamics] Project %s collected %d employees from %d tasks (task-based)', self.id, len(emps), len(tasks))
        return emps

    def _collect_project_poi_ids(self):
        """Collect POI IDs from tasks under this project (df_geodynamics_poi_id)."""
        self.ensure_one()
        tasks = self.env['project.task'].search([('project_id', '=', self.id), ('df_geodynamics_poi_id', '!=', False)])
        poi_ids = set()
        for t in tasks:
            val = getattr(t, 'df_geodynamics_poi_id', False)
            if val:
                poi_ids.add(str(val))
        return poi_ids

    def _collect_existing_timesheet_employees(self, registratie_taak=None):
        """Return employees that already hold Geodynamics registration lines for this project."""
        self.ensure_one()
        domain = [
            ('task_id.project_id', '=', self.id),
            ('name', '=', 'Registratie Geodynamics'),
            ('employee_id', '!=', False),
        ]
        if registratie_taak:
            domain.append(('task_id', '=', registratie_taak.id))
        groups = self.env['account.analytic.line']._read_group(domain, groupby=['employee_id'], aggregates=['__count'])
        emp_ids = {employee.id for employee, count in groups if employee}
        employees = self.env['hr.employee'].browse(list(emp_ids))
        if employees:
            _logger.debug('[Geodynamics] Project %s legacy employees detected=%d', self.id, len(employees))
        return employees

    def _gd_fix_misassigned_clockings(self, project_job_codes):
        """Reassign legacy clockings whose job code doesn't belong to this project."""
        self.ensure_one()
        job_codes = {code for code in (project_job_codes or []) if code}
        if not job_codes:
            return 0, 0
        domain = [
            ('project_id', '=', self.id),
            ('project_code', '!=', False),
            ('project_code', 'not in', list(job_codes)),
        ]
        Clocking = self.env['geodynamics.clocking'].sudo()
        mis_clockings = Clocking.search(domain)
        if not mis_clockings:
            return 0, 0
        project_cache = {}
        Projects = self.env['project.project'].sudo()
        reassigned = 0
        cleared = 0
        for clock in mis_clockings:
            code = clock.project_code
            if code not in project_cache:
                project_cache[code] = Projects.search([('name', 'ilike', code)], limit=1)
            target = project_cache[code]
            vals = {'timesheet_line_id': False}
            if target:
                vals['project_id'] = target.id
                reassigned += 1
            else:
                vals['project_id'] = False
                cleared += 1
            clock.write(vals)
        if reassigned or cleared:
            _logger.info('[Geodynamics] Project %s: re-assigned %d clockings and cleared %d orphan clockings after job-code validation.', self.id, reassigned, cleared)
        return reassigned, cleared

    def _gd_extend_range_with_existing_lines(self, start_date, end_date, registratie_taak):
        """Extend fetch window to include any existing Geodynamics timesheet dates."""
        domain = [
            ('task_id', '=', registratie_taak.id),
            ('name', '=', 'Registratie Geodynamics'),
            ('date', '!=', False),
        ]
        oldest_line = self.env['account.analytic.line'].search(domain, order='date asc', limit=1)
        newest_line = self.env['account.analytic.line'].search(domain, order='date desc', limit=1)
        if oldest_line and oldest_line.date and oldest_line.date < start_date:
            start_date = oldest_line.date
        if newest_line and newest_line.date and newest_line.date > end_date:
            end_date = newest_line.date
        return start_date, end_date

    def _record_matches_poi(self, rec, poi_ids):
        if not poi_ids:
            return False
        pois = rec.get('Pois') if isinstance(rec, dict) else None
        if not pois or not isinstance(pois, (list, tuple)):
            return False
        for p in pois:
            pid = None
            if isinstance(p, dict):
                pid = p.get('Id') or p.get('PoiId') or p.get('POIId') or p.get('id')
            elif isinstance(p, (str, int)):
                pid = p
            if pid is not None and str(pid) in poi_ids:
                return True
        return False

    def _filter_clockings_with_job_codes(self, raw_records, job_codes, handler, poi_ids=None, enable_day_fallback=True):
        """Filter clockings with robust acceptance for multiple daily intervals.
        - Accept start if token in job_codes or POI matches project.
        - Carry forward last valid token **within the same day only** to accept tokenless starts.
        - Retro-accept all earlier tokenless starts within the same day when a provider (token/POI) appears later in that day.
        - Do not skip provider starts; let the pairing logic handle multiple intervals.
        - Keep any stop when there is an open accepted start.
        """
        if not (job_codes or poi_ids):
            return []
        start_types = handler.ACTIVITY_START_TYPES
        end_types = handler.ACTIVITY_END_TYPES
        # Enrich and sort
        enriched = []
        for rec in raw_records:
            if not isinstance(rec, dict):
                continue
            dt = handler._extract_clock_dt(rec)
            if not dt:
                continue
            t = rec.get('Type')
            job_raw = rec.get('JobNumber') or rec.get('JobNumberFull') or rec.get('ActivityNumber')
            token = self._normalize_job_number_token(job_raw)
            has_poi = self._record_matches_poi(rec, poi_ids or set())
            enriched.append({'rec': rec, 'dt': dt, 'type': t, 'token': token, 'has_poi': has_poi})
        enriched.sort(key=lambda x: x['dt'])
        if not enriched:
            return []
        # Pass 1: decide accepted starts (per-day logic)
        accepted_flags = [False] * len(enriched)
        day_pending_indices = []
        last_valid_token = None
        current_day = None
        day_has_provider = False

        def flush_day_pending():
            """Finalize pending starts for the previous day.

            We only retro-accept tokenless starts if that specific day had at least
            one provider (token/POI). We no longer fallback using a token coming
            from previous days to avoid incorrectly assigning later days to an
            earlier JobNumber (e.g., S00577 being reused for 8/12, 9/12).
            """
            nonlocal day_pending_indices, day_has_provider
            if not day_pending_indices:
                return
            if day_has_provider:
                for idx in day_pending_indices:
                    accepted_flags[idx] = True
            day_pending_indices = []
            day_has_provider = False

        for idx, item in enumerate(enriched):
            day = item['dt'].date()
            if day != current_day:
                # New day: finalize previous day's pending starts and reset per-day state
                flush_day_pending()
                current_day = day
                last_valid_token = None  # IMPORTANT: do not carry tokens across days

            if item['type'] in start_types:
                token_ok = (item.get('token') in job_codes) if item.get('token') else False
                poi_ok = bool(item.get('has_poi'))
                if token_ok:
                    last_valid_token = item['token']
                if token_ok or poi_ok:
                    accepted_flags[idx] = True
                    day_has_provider = True
                    # retro-accept all earlier tokenless starts of the same day
                    for p_idx in day_pending_indices:
                        accepted_flags[p_idx] = True
                    day_pending_indices = []
                else:
                    # tokenless start, stage for possible retro-accept or same-day carry-forward
                    # don't accept immediately unless we have a past token **for this day**
                    if enable_day_fallback and last_valid_token is not None:
                        accepted_flags[idx] = True
                    else:
                        day_pending_indices.append(idx)
        # flush last day pending
        flush_day_pending()
        # Pass 2: build selected with pairing counter
        selected = []
        open_count = 0
        for idx, item in enumerate(enriched):
            t = item['type']
            if t in start_types:
                if accepted_flags[idx]:
                    open_count += 1
                    selected.append(item['rec'])
            elif t in end_types:
                if open_count > 0:
                    open_count -= 1
                    selected.append(item['rec'])
        _logger.debug('[Geodynamics] Filter (per-day carry-forward + same-day retro): raw=%d kept=%d job_codes=%s poi=%d', len(raw_records), len(selected), list(job_codes), len(poi_ids or []))
        return selected

    # --- Helpers extracted from fetchClockings ---
    def _gd_generate_chunks(self, d_start, d_end, chunk_days=30):
        cur = d_start
        while cur <= d_end:
            chunk_end = min(cur + timedelta(days=chunk_days - 1), d_end)
            yield cur, chunk_end
            cur = chunk_end + timedelta(days=1)

    def _gd_split_interval_segments(self, start_dt, end_dt):
        """Split [start_dt, end_dt] into day-bounded segments."""
        segs = []
        cur_start = start_dt
        while cur_start.date() < end_dt.date():
            day_end = datetime.combine(cur_start.date(), datetime.min.time()).replace(hour=23, minute=59, second=59)
            segs.append((cur_start, day_end))
            cur_start = day_end + timedelta(seconds=1)
        if end_dt > cur_start:
            segs.append((cur_start, end_dt))
        return segs

    def _gd_ensure_registratie_taak(self, project):
        taak = self.env['project.task'].search([('project_id', '=', project.id), ('name', '=', 'Registratie Geodynamics')], limit=1)
        if not taak:
            taak = self.env['project.task'].create({'project_id': project.id, 'name': 'Registratie Geodynamics'})
        return taak

    def _gd_fetch_raw_clockings_for_employee(self, handler, emp, start_date, end_date):
        total_calls = 0
        total_records = 0
        raw_records_all = []
        for c_start, c_end in self._gd_generate_chunks(start_date, end_date):
            from_dt_str = f"{c_start} 00:00:00"
            to_dt_str = f"{c_end} 23:59:59"
            resp = handler.getClockingsByUserDateRange(emp.df_geodynamics_id, from_dt_str, to_dt_str)
            if resp.get('Success'):
                total_calls += 1
                total_records += resp.get('Count', 0)
                data_part = resp.get('Data') or []
                raw_records_all.extend(data_part)
                _logger.debug("[Geodynamics] Emp %s chunk %s..%s count=%d accum=%d", emp.id, c_start, c_end, resp.get('Count', 0), len(raw_records_all))
            else:
                _logger.warning("[Geodynamics] Emp %s chunk %s..%s fetch error: %s", emp.id, c_start, c_end, resp.get('Error'))
        return raw_records_all, total_calls, total_records

    def _gd_parse_dt(self, v):
        if not v:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v)
            except Exception:
                return None
        return None

    def _gd_minutes_and_hours_between(self, seg_start, seg_end):
        end_of_day_time = datetime.min.replace(hour=23, minute=59, second=59).time()
        minutes_base = int((seg_end - seg_start).total_seconds() // 60)
        minutes_val = minutes_base + 1 if isinstance(seg_end, datetime) and seg_end.time() == end_of_day_time else minutes_base
        hours = round(minutes_val / 60.0, 2)
        return minutes_val, hours

    def _gd_create_or_update_clockings(self, emp, timesheet_line, interval_start, interval_end, raw_records):
        """Create or update geodynamics.clocking records for the interval and link to timesheet.

        Args:
            emp: hr.employee record
            timesheet_line: account.analytic.line record
            interval_start: datetime start of interval
            interval_end: datetime end of interval
            raw_records: list of raw clocking records from API that fall within this interval

        Returns:
            list of geodynamics.clocking records created/updated
        """
        ClockingModel = self.env['geodynamics.clocking']
        created_clockings = []

        for rec in raw_records:
            if not isinstance(rec, dict):
                continue

            # Extract essential fields
            external_id = rec.get('Id') or rec.get('id')
            if not external_id:
                continue

            # Parse datetimes
            date_local_str = rec.get('DateTimeLocal') or rec.get('DateTime')
            date_utc_str = rec.get('DateTimeUtc') or rec.get('DateTimeUTC')

            date_local = ClockingModel._parse_iso_dt(date_local_str, assume_utc_if_naive=False) if date_local_str else False
            date_utc = ClockingModel._parse_iso_dt(date_utc_str, assume_utc_if_naive=True) if date_utc_str else False

            # Check if clocking already exists
            existing_clocking = ClockingModel.search([('external_id', '=', str(external_id))], limit=1)

            clocking_vals = {
                'external_id': str(external_id),
                'date_local': date_local,
                'date_utc': date_utc,
                'type': rec.get('Type'),
                'type_label': rec.get('TypeLabel') or rec.get('Type'),
                'job_number': rec.get('JobNumber') or rec.get('JobNumberFull') or rec.get('ActivityNumber'),
                'description': rec.get('Description'),
                'note': rec.get('Note'),
                'is_manual': ClockingModel._parse_bool(rec.get('IsManual')),
                'woon_werk': ClockingModel._parse_bool(rec.get('WoonWerk')),
                'absence_code': rec.get('AbsenceCode'),
                'external_code': rec.get('ExternalCode'),
                'external_type': rec.get('ExternalType'),
                'location': rec.get('Location'),
                'pois': rec.get('Pois'),
                'user': rec.get('User'),
                'user_id_geodynamics': str(rec.get('User', {}).get('Id')) if isinstance(rec.get('User'), dict) else False,
                'vehicle': rec.get('Vehicle'),
                'vehicle_code': rec.get('Vehicle', {}).get('Code') if isinstance(rec.get('Vehicle'), dict) else False,
                'raw_payload': rec,
                'employee_id': emp.id,
                'project_id': timesheet_line.task_id.project_id.id if timesheet_line.task_id else False,
                'timesheet_line_id': timesheet_line.id,  # Link to timesheet
            }

            if existing_clocking:
                # Update existing clocking and link to timesheet
                existing_clocking.write({
                    'timesheet_line_id': timesheet_line.id,
                    'employee_id': emp.id,
                    'project_id': timesheet_line.task_id.project_id.id if timesheet_line.task_id else False,
                })
                created_clockings.append(existing_clocking)
            else:
                # Create new clocking
                new_clocking = ClockingModel.create(clocking_vals)
                created_clockings.append(new_clocking)

        return created_clockings

    def _gd_write_or_update_interval_line(self, project, taak, emp, seg_start, seg_end, hours):
        seg_date = seg_start.date()
        domain = [
            ('account_id', '=', project.account_id.id),
            ('task_id', '=', taak.id),
            ('employee_id', '=', emp.id),
            ('df_start_time', '=', seg_start),
            ('df_end_time', '=', seg_end),
        ]
        ts_line = self.env['account.analytic.line'].search(domain, limit=1)
        vals = {
            'account_id': project.account_id.id,
            'date': seg_date,
            'task_id': taak.id,
            'employee_id': emp.id,
            'name': 'Registratie Geodynamics',
            'unit_amount': hours,
            'df_start_time': seg_start,
            'df_end_time': seg_end,
        }
        if ts_line:
            ts_line.write({'unit_amount': hours})
            return ts_line, 1, 0  # line, updated, created
        # Fallback: reuse same-day line without start/end, but only lines that belong to Geodynamics registration name
        fallback_domain = [
            ('account_id', '=', project.account_id.id),
            ('task_id', '=', taak.id),
            ('employee_id', '=', emp.id),
            ('date', '=', seg_date),
            ('name', '=', 'Registratie Geodynamics'),
            ('df_start_time', '=', False),
            ('df_end_time', '=', False),
        ]
        ts_fallback = self.env['account.analytic.line'].search(fallback_domain, limit=1)
        if ts_fallback:
            ts_fallback.write({
                'unit_amount': hours,
                'df_start_time': seg_start,
                'df_end_time': seg_end,
                'name': 'Registratie Geodynamics',
                'date': seg_date,
            })
            return ts_fallback, 1, 0
        new_line = self.env['account.analytic.line'].create(vals)
        return new_line, 0, 1

    def _gd_add_group_extra_lines(self, project, taak, emp, days_set):
        """Add/update extra timesheet lines per day for employee timesheet groups.
        For each date in days_set, add one line per active employee.timesheet.group with its extra_time (minutes) converted to hours.
        Only add if total Geodynamics registered minutes for that day >= group's minimum_time (minutes).
        Returns tuple (updated_count, created_count)."""
        groups = getattr(emp, 'df_timesheet_group_ids', self.env['employee.timesheet.group'])
        if not groups:
            return 0, 0
        created = 0
        updated = 0
        for ddate in sorted(days_set):
            total_minutes_domain = [
                ('account_id', '=', project.account_id.id),
                ('task_id', '=', taak.id),
                ('employee_id', '=', emp.id),
                ('date', '=', ddate),
                ('name', '=', 'Registratie Geodynamics'),
            ]
            existing_reg_lines = self.env['account.analytic.line'].search(total_minutes_domain)
            total_hours = sum(existing_reg_lines.mapped('unit_amount'))
            total_minutes = int(total_hours * 60)
            for grp in groups.filtered(lambda g: g.active and (g.extra_time or 0) > 0):
                minimum_time = int(grp.minimum_time or 0)
                if minimum_time > 0 and total_minutes < minimum_time:
                    _logger.debug("[Geodynamics] Skip extra line emp=%s date=%s group='%s': total_minutes=%d < minimum_time=%d", emp.id, ddate, grp.name, total_minutes, minimum_time)
                    continue
                minutes = int(grp.extra_time or 0)
                hours = round(minutes / 60.0, 2)
                domain = [
                    ('account_id', '=', project.account_id.id),
                    ('task_id', '=', taak.id),
                    ('employee_id', '=', emp.id),
                    ('date', '=', ddate),
                    ('name', '=', grp.name),
                ]
                line = self.env['account.analytic.line'].search(domain, limit=1)
                vals = {
                    'account_id': project.account_id.id,
                    'task_id': taak.id,
                    'employee_id': emp.id,
                    'date': ddate,
                    'name': grp.name,
                    'unit_amount': hours,
                    'df_start_time': False,
                    'df_end_time': False,
                }
                if line:
                    if abs(line.unit_amount - hours) > 1e-6:
                        line.write({'unit_amount': hours})
                        updated += 1
                else:
                    self.env['account.analytic.line'].create(vals)
                    created += 1
        return updated, created

    def _gd_cleanup_redundant_lines(self, project, taak, emp, start_date, end_date, valid_interval_keys):
        """Remove redundant 'Registratie Geodynamics' timesheet lines for this employee/task/date range
        that don't match any computed (df_start_time, df_end_time) interval or are missing start/end.
        Does not touch group extra lines (different names)."""
        cleanup_domain = [
            ('account_id', '=', project.account_id.id),
            ('task_id', '=', taak.id),
            ('employee_id', '=', emp.id),
            ('date', '>=', start_date),
            ('date', '<=', end_date),
            ('name', '=', 'Registratie Geodynamics'),
        ]
        existing_lines = self.env['account.analytic.line'].search(cleanup_domain)
        removed = 0
        for line in existing_lines:
            st = getattr(line, 'df_start_time', False)
            et = getattr(line, 'df_end_time', False)
            if not st or not et or (st, et) not in valid_interval_keys:
                line.unlink()
                removed += 1
        if removed:
            _logger.debug("[Geodynamics] Cleanup for emp %s: removed %d redundant lines", emp.id, removed)

    def _gd_repair_legacy_lines(self, project, taak, emp, start_date, end_date, valid_interval_keys, touched_dates):
        """Ensure legacy lines inside the range are rebuilt from fresh intervals.

        - Remove any Geodynamics lines whose (start,end) pair is not freshly computed.
        - Drop lines missing start/end or sitting on untouched dates inside the window.
        - Returns number of deletions performed.
        """
        domain = [
            ('account_id', '=', project.account_id.id),
            ('task_id', '=', taak.id),
            ('employee_id', '=', emp.id),
            ('date', '>=', start_date),
            ('date', '<=', end_date),
            ('name', '=', 'Registratie Geodynamics'),
        ]
        lines = self.env['account.analytic.line'].search(domain)
        removed = 0
        for line in lines:
            st = getattr(line, 'df_start_time', False)
            et = getattr(line, 'df_end_time', False)
            if not st or not et:
                line.unlink()
                removed += 1
                continue
            if (st, et) not in valid_interval_keys:
                line.unlink()
                removed += 1
                continue
            if touched_dates and line.date not in touched_dates:
                # Legacy interval not recomputed this round; drop to force rebuild on next fetch
                line.unlink()
                removed += 1
        if removed:
            _logger.debug('[Geodynamics] Legacy repair removed %d lines for emp %s', removed, emp.id)
        return removed

    def fetchClockings(self):
        """Fetch clockings for each linked employee using project date range.
        Date range logic (updated) delegated to _compute_geodynamics_clocking_range.
        Create timesheet entries per interval per day instead of a daily total.
        Only clockings whose JobNumber (prefix token) matches a code extracted from the project name
        (pattern S\d{5}) are counted. If no such job code is present in the project name, no clockings
        are counted.
        Also cleans up same-day timesheet lines that don't match computed intervals.
        """
        company, login, password = self._get_geodynamic_configs()
        if not (company and login and password):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Geodynamics',
                    'message': 'Missing Geodynamics credentials in Settings.',
                    'type': 'danger',
                    'sticky': False,
                }
            }
        handler = GeodynamicsHandler(login, password, company, self.env)
        total_calls = 0
        total_records = 0
        total_active_minutes = 0
        created_lines = 0
        updated_lines = 0
        legacy_repaired_lines = 0
        for project in self:
            if not project.account_id:
                continue
            start_date, end_date = project._compute_geodynamics_clocking_range()
            project_job_codes = project._extract_project_job_codes()
            reassign_count, cleared_count = project._gd_fix_misassigned_clockings(project_job_codes)
            project_poi_ids = project._collect_project_poi_ids()
            registratie_taak = project._gd_ensure_registratie_taak(project)
            # Always pull fresh API data to ensure legacy clockings are rebuilt even if previous runs mis-assigned records.
            raw_data_by_employee = {}
            legacy_emps = project._collect_existing_timesheet_employees(registratie_taak)
            task_employees = project._collect_task_employees()
            employee_scope = (task_employees | legacy_emps).filtered(lambda e: e.df_geodynamics_id)
            _logger.debug(
                "[Geodynamics] Fetch clockings project=%s job_codes=%s poi_ids=%d full_range=%s..%s employees=%d legacy=%d",
                project.id,
                list(project_job_codes),
                len(project_poi_ids),
                start_date,
                end_date,
                len(task_employees),
                len(legacy_emps),
            )
            for emp in employee_scope:
                start_date_emp, end_date_emp = project._gd_extend_range_with_existing_lines(start_date, end_date, registratie_taak)
                raw_records_all, calls, recs = raw_data_by_employee.get(emp.id, (None, 0, 0))
                if raw_records_all is None:
                    raw_records_all, calls, recs = project._gd_fetch_raw_clockings_for_employee(handler, emp, start_date_emp, end_date_emp)
                    raw_data_by_employee[emp.id] = (raw_records_all, calls, recs)
                total_calls += calls
                total_records += recs
                # --- Process fetched data (same for legacy and task-based employees) ---
                if not raw_records_all:
                    _logger.warning("[Geodynamics] Project %s employee %s: no clocking records found in range %s..%s", project.id, emp.id, start_date_emp, end_date_emp)
                    continue
                # Filter & select relevant clocking records
                selected_records = project._filter_clockings_with_job_codes(raw_records_all, project_job_codes, handler, project_poi_ids)
                if not selected_records:
                    _logger.warning("[Geodynamics] Project %s employee %s: no valid clocking records found in range %s..%s", project.id, emp.id, start_date_emp, end_date_emp)
                    continue
                # --- Compute intervals from selected records ---
                # Split into day-bounded segments
                all_segments = []
                for rec in selected_records:
                    dt = handler._extract_clock_dt(rec)
                    if not dt:
                        continue
                    day_segs = project._gd_split_interval_segments(dt, dt)
                    all_segments.extend(day_segs)
                all_segments = sorted(set(all_segments))  # remove duplicates, sort
                _logger.debug("[Geodynamics] Project %s employee %s: computed %d clocking segments from %d records", project.id, emp.id, len(all_segments), len(selected_records))
                if not all_segments:
                    continue
                # Compute minutes per segment
                segment_minutes = {}
                for seg_start, seg_end in all_segments:
                    minutes_val, hours_val = project._gd_minutes_and_hours_between(seg_start, seg_end)
                    segment_minutes[(seg_start, seg_end)] = minutes_val
                # Detect full-day gaps in between
                full_days = timedelta(days=1)
                for (seg_start_a, seg_end_a), (seg_start_b, seg_end_b) in zip(all_segments[:-1], all_segments[1:]):
                    gap = seg_start_b - seg_end_a
                    if gap >= full_days:
                        # Found a gap of at least one full day; insert a zero-minute segment
                        middle = seg_end_a + timedelta(seconds=1)
                        segment_minutes[(seg_end_a, middle)] = 0
                        _logger.debug("[Geodynamics] Project %s employee %s: inserted zero-minute segment due to gap", project.id, emp.id)
                # --- Create or update timesheet lines ---
                # Group by (date, task_id, employee_id) for line creation
                interval_keys = {}
                for (seg_start, seg_end), minutes in segment_minutes.items():
                    seg_date = seg_start.date()
                    domain = [
                        ('account_id', '=', project.account_id.id),
                        ('task_id', '=', registratie_taak.id),
                        ('employee_id', '=', emp.id),
                        ('date', '=', seg_date),
                    ]
                    ts_line = self.env['account.analytic.line'].search(domain, limit=1)
                    if ts_line:
                        # Update existing line
                        ts_line.write({'unit_amount': minutes / 60.0})
                        updated_lines += 1
                        interval_keys[(seg_start, seg_end)] = True
                    else:
                        # New line needed
                        new_line, new_updated, new_created = project._gd_write_or_update_interval_line(project, registratie_taak, emp, seg_start, seg_end, minutes / 60.0)
                        created_lines += new_created
                        updated_lines += new_updated
                        interval_keys[(seg_start, seg_end)] = True
                # Cleanup: remove any redundant lines that may have been left in place
                project._gd_cleanup_redundant_lines(project, registratie_taak, emp, start_date_emp, end_date_emp, interval_keys)
                # Repair legacy lines: ensure any legacy lines in the range are either updated or removed
                legacy_repaired_lines += project._gd_repair_legacy_lines(project, registratie_taak, emp, start_date_emp, end_date_emp, interval_keys, None)
        # --- Summary notification ---
        summary_lines = []
        if created_lines > 0:
            summary_lines.append(f"{created_lines} nieuwe tijdregistratie(s) aangemaakt.")
        if updated_lines > 0:
            summary_lines.append(f"{updated_lines} tijdregistratie(s) bijgewerkt.")
        if legacy_repaired_lines > 0:
            summary_lines.append(f"{legacy_repaired_lines} legacy tijdregistratie(s) hersteld.")
        if summary_lines:
            summary_message = "Geodynamics tijdregistraties verwerkt:\n" + "\n".join(summary_lines)
            _logger.info("[Geodynamics] " + summary_message)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Geodynamics',
                    'message': summary_message,
                    'type': 'success',
                    'sticky': False,
                }
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Geodynamics',
                'message': 'Geen tijdregistraties gevonden of bijgewerkt.',
                'type': 'info',
                'sticky': False,
            }
        }

    def sendPlanningToDGd(self):
        company, login, password = self._get_geodynamic_configs()

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        try:
            ws = float(self.env['ir.config_parameter'].sudo().get_param('geodynamics.workday_start', '6.0'))
            we = float(self.env['ir.config_parameter'].sudo().get_param('geodynamics.workday_end', '15.0'))
        except (ValueError, TypeError):
            ws, we = 6.0, 15.0
        start_hour, start_min = int(ws), int((ws % 1) * 60)
        end_hour, end_min = int(we), int((we % 1) * 60)

        user_tz_name = self.env.user.tz or self.env.context.get('tz') or 'Europe/Brussels'
        try:
            user_tz = pytz.timezone(user_tz_name)
        except Exception:
            user_tz = pytz.timezone('Europe/Brussels')

        for record in self:
            _logger.debug('date_start: %s', record.date_start)
            _logger.debug('date: %s', record.date)

            # Clear existing plannings for this project first so re-planning (e.g.
            # after adding an employee) does not create duplicate entries.
            self.env['df.geodynamics.planning'].search([('project_id', '=', record.id)]).unlink()

            current_date = record.date_start
            while current_date <= record.date:
                _logger.debug('current_date: %s', current_date)

                local_start = user_tz.localize(datetime.combine(current_date, datetime.min.time()).replace(
                    hour=start_hour, minute=start_min))
                local_end = user_tz.localize(datetime.combine(current_date, datetime.min.time()).replace(
                    hour=end_hour, minute=end_min))
                utc_start = local_start.astimezone(pytz.utc).replace(tzinfo=None)
                utc_end = local_end.astimezone(pytz.utc).replace(tzinfo=None)

                for emp in record.df_gd_employee_ids:
                    sId = gdHandler.createPlanning(emp.df_geodynamics_id, utc_start, utc_end, record.df_gd_name, description=record.name)
                    self.env['df.geodynamics.planning'].create({
                        'start_datetime': utc_start,
                        'end_datetime': utc_end,
                        'id_geodynamics': sId,
                        'user_id_geodynamics': emp.df_geodynamics_id,
                        'employee_id': emp.id,
                        'project_id': record.id,
                        'activitynumber': record.df_gd_name,
                        'description': record.name,
                    })

                current_date += timedelta(days=1)

        return self._gd_notify('Geodynamics', 'success', 'Planning verstuurd naar Geodynamics.')

    def _calculate_time_difference(self, start, stop):
        start_time = datetime.fromisoformat(start)
        stop_time = datetime.fromisoformat(stop)
        time_difference = (stop_time - start_time).total_seconds() / 3600
        return {'start': start_time, 'stop': stop_time, 'diff': time_difference}

    def _resolve_fleet_vehicle(self, resource_id):
        if not resource_id:
            return False
        vehicle = self.env['fleet.vehicle'].search([('df_geodynamics_id', '=', resource_id)], limit=1)
        return vehicle.id if vehicle else False

    def _get_allowed_event_types(self):
        codes_str = self.env['ir.config_parameter'].sudo().get_param('geodynamics.import_event_types', '')
        if not codes_str:
            return None
        return set(c.strip() for c in codes_str.split(',') if c.strip())

    def _gd_notify(self, title, ntype, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title, 'type': ntype, 'message': message, 'sticky': True,
                # Reload the current view after the notification so freshly created
                # timesheet lines appear without a manual page refresh.
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def laadPostcalc(self):
        company, login, password = self._get_geodynamic_configs()
        postcalcsource = self.env['ir.config_parameter'].sudo().get_param('geodynamics.postcalcsource') or 'postcalculation'
        allowed_types = self._get_allowed_event_types()
        raw_event_types = self.env['ir.config_parameter'].sudo().get_param('geodynamics.import_event_types', '')
        _logger.info('[Geodynamics][Postcalc] Event Types to Import (from res.config.settings): raw=%r -> %s | source=%s',
                     raw_event_types, sorted(allowed_types) if allowed_types else '(empty = all types)', postcalcsource)

        if not (company and login and password):
            _logger.warning('[Geodynamics][Postcalc] Missing credentials for project post-calculation')
            return self._gd_notify('Geodynamics', 'danger', 'Geodynamics credentials ontbreken in de instellingen.')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        total_created = 0
        data_returned = False
        seen_keys = set()
        skipped_types = set()

        for record in self:
            # Project key pushed as ActivityNumber; the id part is "P<id>".
            expected_key = record.df_gd_name
            expected_id = 'P%s' % record.id
            _logger.info('[Geodynamics][Postcalc] === Project %s "%s" key=%r ===', record.id, record.name, expected_key)

            registratieTaak = self.env['project.task'].search(
                [('project_id', '=', record.id), ('name', '=', 'Registratie Geodynamics')], limit=1)
            if not registratieTaak:
                registratieTaak = self.env['project.task'].create(
                    {'project_id': record.id, 'name': 'Registratie Geodynamics'})

            if not record.df_gd_employee_ids:
                _logger.warning('[Geodynamics][Postcalc] Project %s: no Geodynamics employees selected', record.id)
                continue

            current_date = record.date_start or fields.Date.context_today(self)
            end_date = record.date or current_date
            while current_date <= end_date:
                for emp in record.df_gd_employee_ids:
                    if not emp.df_geodynamics_id:
                        continue
                    _logger.info('[Geodynamics][Postcalc] Fetch emp=%s (gd=%s) date=%s', emp.name, emp.df_geodynamics_id, current_date)
                    data = gdHandler.laadPostcalc(emp.df_geodynamics_id, self.date_to_datetime(current_date, 0, 0))
                    if isinstance(data, dict) and data.get('Data'):
                        data_returned = True

                    self.env['account.analytic.line'].search([
                        ('account_id', '=', record.account_id.id),
                        ('employee_id', '=', emp.id),
                        ('date', '=', current_date),
                        ('task_id', '=', registratieTaak.id),
                    ]).unlink()

                    # Reuse the task-level processor, matched on the project key.
                    created, keys, sk = registratieTaak._process_postcalc_data(
                        data, registratieTaak, emp, current_date, postcalcsource, allowed_types,
                        filter_by_job=True, expected_key=expected_key, expected_id=expected_id)
                    total_created += created
                    seen_keys |= keys
                    skipped_types |= sk

                current_date += timedelta(days=1)

        _logger.info('[Geodynamics][Postcalc] DONE (project): %d line(s) created, data_returned=%s, keys seen=%s, expected=%s',
                     total_created, data_returned, sorted(seen_keys), self.mapped('df_gd_name'))

        if total_created:
            return self._gd_notify('Geodynamics Post-calculatie', 'success',
                                   '%d Registratie Geodynamics regel(s) aangemaakt.' % total_created)
        if skipped_types:
            return self._gd_notify(
                'Geodynamics Post-calculatie', 'warning',
                'Geen registraties aangemaakt. Er zijn events gevonden voor dit project, maar hun type (%s) '
                'staat niet in "Event Types to Import" (%s).\nPas de instelling aan in de Geodynamics-instellingen.'
                % (', '.join(sorted(str(t) for t in skipped_types)),
                   ', '.join(sorted(allowed_types)) if allowed_types else '(leeg)'))
        if data_returned and seen_keys:
            return self._gd_notify(
                'Geodynamics Post-calculatie', 'warning',
                'Geen registraties aangemaakt. Er zijn wel events gevonden, maar de kostenplaats/jobnummer '
                'kwam niet overeen met het project.\nGevonden: %s\nVerwacht: %s'
                % (', '.join(sorted(seen_keys)), ', '.join(self.mapped('df_gd_name'))))
        return self._gd_notify(
            'Geodynamics Post-calculatie', 'warning',
            'Geen post-calculatie data gevonden in Geodynamics voor dit project/periode.')


    def date_to_datetime(self, d, hours, minutes):
        return datetime.combine(d, datetime.min.time().replace(hour=hours, minute=minutes))
