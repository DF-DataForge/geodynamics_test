# -*- coding: utf-8 -*-
from odoo import models, api, fields
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import logging
import pytz

_logger = logging.getLogger(__name__)


class GeodynamicsCron(models.Model):
    _name = 'geodynamics.cron'
    _description = 'Geodynamics scheduled helpers'

    name = fields.Char(string='Name')

    # ------------------------------------------------------------------
    # Startup script
    # ------------------------------------------------------------------
    def init(self):
        """Startup hook executed on every module install/upgrade (each deploy).

        When the current database has been neutralized (e.g. a production copy
        restored on a test/staging server), the Enterprise subscription
        expiration date still points at the production value and could lock the
        database. To keep neutralized copies usable, push the expiration date
        two months into the future.
        """
        super().init()
        self._extend_expiration_if_neutralized()

    @api.model
    def _extend_expiration_if_neutralized(self):
        """If the database is neutralized, set its expiration date to now + 2 months."""
        params = self.env['ir.config_parameter'].sudo()

        # Odoo sets 'database.is_neutralized' when a database is neutralized.
        is_neutralized = params.get_param('database.is_neutralized')
        if not is_neutralized or str(is_neutralized).lower() in ('false', '0'):
            return

        new_expiration = fields.Datetime.now() + relativedelta(months=2)
        new_expiration_str = fields.Datetime.to_string(new_expiration)
        params.set_param('database.expiration_date', new_expiration_str)
        _logger.info(
            "Neutralized database detected on startup: 'database.expiration_date' "
            "set to %s (now + 2 months).", new_expiration_str,
        )

    @api.model
    def _get_credentials(self):
        # Try to read stored config parameters (match keys used in res_config_settings)
        params = self.env['ir.config_parameter'].sudo()
        # res_config_settings uses 'geodynamics.username' for the login field
        login = params.get_param('geodynamics.username') or params.get_param('geodynamics.login') or params.get_param('geodynamics_login')
        password = params.get_param('geodynamics.password') or params.get_param('geodynamics_password')
        company = params.get_param('geodynamics.company') or params.get_param('geodynamics_company')
        return login, password, company

    @api.model
    def _get_woon_werk_vehicle_codes(self):
        """Get list of vehicle codes allowed for woon-werk calculation from settings.

        Returns:
            set: Set of vehicle codes (uppercase, stripped). Empty set means all vehicles allowed.
        """
        params = self.env['ir.config_parameter'].sudo()
        codes_str = params.get_param('geodynamics.woon_werk_vehicle_codes', '')
        if not codes_str:
            return set()  # Empty set means all vehicles allowed
        # Split by comma, strip whitespace, convert to uppercase, filter empty strings
        codes = {code.strip().upper() for code in codes_str.split(',') if code.strip()}
        return codes

    @api.model
    def _is_vehicle_allowed_for_woon_werk(self, vehicle_data):
        """Check if a vehicle is allowed for woon-werk calculation based on settings.

        Args:
            vehicle_data: dict with Vehicle data from API (should have 'Code' key)

        Returns:
            bool: True if vehicle is allowed, False otherwise
        """
        allowed_codes = self._get_woon_werk_vehicle_codes()
        # If no codes configured, allow all vehicles
        if not allowed_codes:
            return True

        # Check if vehicle has a code and if it's in the allowed list
        if not isinstance(vehicle_data, dict):
            return False

        vehicle_code = vehicle_data.get('Code') or ''
        vehicle_code = vehicle_code.strip().upper() if vehicle_code else ''
        if not vehicle_code:
            return False

        return vehicle_code in allowed_codes

    @api.model
    def _compute_movement_distance_for_type12(self, handler, type12_items, group_day, movement_cache, is_raw_records=True):
        """Compute movement_distance for Movement Drive (Type==12) records using location status API.

        Logic: For each Type==12 Movement, find all Bars that fall within the Movement's start/stop time range,
        then sum up their MileageDriven values to get the total distance traveled.

        Args:
            handler: GeodynamicsHandler instance
            type12_items: List of Type==12 items (either raw dicts with 'rec'/'dt' keys or odoo records)
            group_day: date object for the day to process
            movement_cache: dict cache by (vehicle_id, day) to avoid repeated API calls
            is_raw_records: bool - True if type12_items contains raw API records, False if odoo records

        Returns:
            int: number of records updated
        """
        if isinstance(group_day, datetime):
            group_day_date = group_day.date()
        else:
            group_day_date = group_day
        day_from = datetime.combine(group_day_date, datetime.min.time())
        day_to = datetime.combine(group_day_date, datetime.max.time()).replace(microsecond=0)

        updated = 0
        for item in type12_items:
            # Extract vehicle_id, movement start time and end time based on record type
            vehicle_id = None
            movement_start_dt = None
            movement_end_dt = None

            if is_raw_records:
                # Raw API records: item has 'rec' and 'dt' keys
                rec = item.get('rec') if isinstance(item, dict) else None
                if isinstance(rec, dict):
                    v = rec.get('Vehicle')
                    if isinstance(v, dict):
                        vehicle_id = v.get('Id')
                    # Get Movement start time from DateTimeLocal or Start field
                    movement_start_dt = item.get('dt')
                    if not movement_start_dt:
                        start_str = rec.get('Start') or rec.get('DateTimeLocal')
                        if start_str:
                            try:
                                movement_start_dt = handler._parse_input_dt(start_str)
                            except Exception as e:
                                _logger.debug('Failed to parse Start time for Movement: %s, error: %s', start_str, e)
                    # Get Movement end time from Stop field
                    stop_str = rec.get('Stop')
                    if stop_str:
                        try:
                            movement_end_dt = handler._parse_input_dt(stop_str)
                        except Exception as e:
                            _logger.debug('Failed to parse Stop time for Movement: %s, error: %s', stop_str, e)
            else:
                # Odoo records
                rec = item
                if isinstance(item.vehicle, dict):
                    vehicle_id = item.vehicle.get('Id')
                # Try raw payload as backup
                if not vehicle_id and isinstance(item.raw_payload, dict):
                    v = item.raw_payload.get('Vehicle')
                    if isinstance(v, dict):
                        vehicle_id = v.get('Id')
                # Get Movement start time
                movement_start_dt = item.date_local
                if not movement_start_dt and isinstance(item.raw_payload, dict):
                    start_str = item.raw_payload.get('Start') or item.raw_payload.get('DateTimeLocal')
                    if start_str:
                        try:
                            movement_start_dt = handler._parse_input_dt(start_str)
                        except Exception as e:
                            _logger.debug('Failed to parse Start time from raw_payload: %s, error: %s', start_str, e)
                # Get Movement end time from stop_time field or raw_payload
                movement_end_dt = item.stop_time
                if not movement_end_dt and isinstance(item.raw_payload, dict):
                    stop_str = item.raw_payload.get('Stop')
                    if stop_str:
                        try:
                            movement_end_dt = handler._parse_input_dt(stop_str)
                        except Exception as e:
                            _logger.debug('Failed to parse Stop time from raw_payload: %s, error: %s', stop_str, e)

            if not vehicle_id:
                _logger.debug('Skipping Movement record without vehicle_id: %s', rec if is_raw_records else item.id)
                continue

            if not movement_start_dt or not movement_end_dt:
                _logger.debug('Skipping Movement record without start/end time, vehicle: %s, start: %s, end: %s',
                            vehicle_id, movement_start_dt, movement_end_dt)
                continue

            # Get or build bars_list from cache - stores all bars with their details
            cache_key = (vehicle_id, group_day_date)
            bars_list = movement_cache.get(cache_key)
            if bars_list is None:
                bars_list = []
                try:
                    status_res = handler.getLocationStatus(vehicle_id, day_from, day_to, raise_on_error=False)
                except Exception as e:
                    _logger.exception('Error calling getLocationStatus for %s on %s: %s', vehicle_id, group_day_date, e)
                    status_res = None

                if status_res and status_res.get('Success'):
                    data = status_res.get('Data')
                    _logger.info('LocationStatus API response for vehicle %s: data type=%s', vehicle_id, type(data))

                    results = []
                    if isinstance(data, dict):
                        # Try StatusResults first
                        res_list = data.get('StatusResults')
                        if isinstance(res_list, list):
                            results = res_list
                            _logger.info('Found StatusResults with %d items', len(results))
                        else:
                            # Maybe data itself contains Bars?
                            if 'Bars' in data:
                                results = [data]
                                _logger.info('Found Bars directly in data dict')
                    elif isinstance(data, list):
                        results = data
                        _logger.info('Data is list with %d items', len(data))

                    # Build list of bars with their Start, Stop, and MileageDriven
                    bars_count = 0
                    for res_item in results:
                        if not isinstance(res_item, dict):
                            continue
                        bars = res_item.get('Bars')
                        if not isinstance(bars, list):
                            _logger.debug('No Bars list in result item for vehicle %s', vehicle_id)
                            continue

                        bars_count += len(bars)
                        for bar in bars:
                            if not isinstance(bar, dict):
                                continue
                            try:
                                # Parse Start and Stop times
                                bar_start_dt = None
                                bar_stop_dt = None
                                start_s = bar.get('Start')
                                stop_s = bar.get('Stop')

                                if start_s:
                                    bar_start_dt = handler._parse_input_dt(start_s)
                                if stop_s:
                                    bar_stop_dt = handler._parse_input_dt(stop_s)

                                if bar_start_dt and bar_stop_dt:
                                    # Get MileageDriven
                                    mileage_driven = bar.get('MileageDriven')
                                    if isinstance(mileage_driven, (int, float)):
                                        bars_list.append({
                                            'start': bar_start_dt,
                                            'stop': bar_stop_dt,
                                            'mileage_driven': float(mileage_driven)
                                        })
                                        _logger.debug('Added Bar: start=%s, stop=%s, mileage_driven=%.2f',
                                                    bar_start_dt, bar_stop_dt, mileage_driven)
                                    else:
                                        _logger.debug('Skipping Bar with invalid MileageDriven: %s', mileage_driven)
                                else:
                                    _logger.debug('Skipping Bar without valid Start/Stop: start=%s, stop=%s', start_s, stop_s)
                            except Exception as e:
                                log_prefix = 'Backfill:' if not is_raw_records else ''
                                _logger.debug('%s failed parsing Bar: %s, error: %s', log_prefix, bar, e)

                    _logger.info('Processed %d Bars for vehicle %s, extracted %d valid bars with mileage',
                                bars_count, vehicle_id, len(bars_list))
                else:
                    _logger.warning('LocationStatus API failed or returned no success for vehicle %s: %s',
                                  vehicle_id, status_res)

                movement_cache[cache_key] = bars_list

            # Find all Bars that fall within the Movement's time range and sum their MileageDriven
            try:
                total_mileage = 0.0
                matched_bars_count = 0

                if bars_list:
                    for bar in bars_list:
                        bar_start = bar['start']
                        bar_stop = bar['stop']

                        # Check if Bar overlaps with Movement time range
                        # Bar is included if there's any overlap: bar starts before movement ends AND bar ends after movement starts
                        if bar_start < movement_end_dt and bar_stop > movement_start_dt:
                            total_mileage += bar['mileage_driven']
                            matched_bars_count += 1
                            _logger.debug('Matched Bar (overlap): start=%s, stop=%s, mileage=%.2f',
                                        bar_start, bar_stop, bar['mileage_driven'])

                    log_prefix = 'Backfill:' if not is_raw_records else ''
                    _logger.info('%s Movement [%s - %s]: matched %d bars (overlap), total mileage: %.2f km',
                               log_prefix, movement_start_dt, movement_end_dt, matched_bars_count, total_mileage)
                else:
                    _logger.warning('Empty bars_list for vehicle %s on %s', vehicle_id, group_day_date)

                if total_mileage > 0:
                    if is_raw_records:
                        # Set on raw dict
                        if isinstance(rec, dict):
                            rec['movement_distance'] = float(total_mileage)
                            updated += 1
                    else:
                        # Write to odoo record
                        rec.write({'movement_distance': float(total_mileage)})
                        updated += 1
                else:
                    log_prefix = 'Backfill:' if not is_raw_records else ''
                    _logger.debug('%s No bars matched for Movement [%s - %s], vehicle %s',
                                 log_prefix, movement_start_dt, movement_end_dt, vehicle_id)
            except Exception as e:
                log_prefix = 'Backfill:' if not is_raw_records else ''
                if is_raw_records:
                    _logger.exception('%s Could not set movement_distance for rec (raw): %s, error: %s', log_prefix, rec, e)
                else:
                    _logger.exception('%s failed to write movement_distance for record %s, error: %s', log_prefix, rec.id, e)

        return updated

    @api.model
    def _assign_projects_for_date(self, target_date):
        """Assign project_id on geodynamics.clocking for a given date, emulating
        the same job code/POI matching logic as project.fetchClockings, but
        working from persisted clocking records instead of raw API data.

        This ensures that clockings fetched via cron/wizard are linked to the
        correct project in the same way as when using the project-level fetch.
        """
        if isinstance(target_date, datetime):
            target_date = target_date.date()

        # Compute date range in local time
        date_start = datetime.combine(target_date, datetime.min.time())
        date_end = datetime.combine(target_date, datetime.max.time())

        Clocking = self.env['geodynamics.clocking'].sudo()
        Project = self.env['project.project'].sudo()

        # Stats for logging project code mappings
        project_code_stats = {
            'mapped': {},   # code -> set(project_ids)
            'unmapped': set(),  # codes seen but not matched to any project
        }

        # Fetch all clockings for the day
        clockings = Clocking.search([
            ('date_local', '>=', date_start),
            ('date_local', '<=', date_end),
        ])
        if not clockings:
            _logger.info('Project assignment: no clockings found for %s', target_date)
            return

        # Precompute project job codes and POI ids similar to project.py helpers
        projects = Project.search([])
        project_job_map = {}
        project_poi_map = {}
        for proj in projects:
            try:
                job_codes = proj._extract_project_job_codes() or set()
            except Exception:
                job_codes = set()
            try:
                poi_ids = proj._collect_project_poi_ids() or set()
            except Exception:
                poi_ids = set()
            if job_codes or poi_ids:
                project_job_map[proj.id] = job_codes
                project_poi_map[proj.id] = poi_ids
                # Track which codes belong to which project for logging
                for code in job_codes:
                    project_code_stats['mapped'].setdefault(code, set()).add(proj.id)

        if not project_job_map:
            _logger.info('Project assignment: no projects with job codes or POIs configured')
            return

        # Helper: normalize job token as in project._normalize_job_number_token
        import re as _re

        def _normalize_job_number_token(raw):
            if not raw:
                return None
            token = str(raw).split(' - ')[0].strip().upper()
            m = _re.match(r'^(S\d+)$', token)
            return m.group(1) if m else None

        def _record_matches_poi(rec, poi_ids):
            if not poi_ids:
                return False
            pois = rec.pois if rec.pois is not None else None
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

        # Group clockings by employee and day to apply per-day matching logic
        groups = {}
        for c in clockings:
            day = (c.date_local or c.date_utc).date() if (c.date_local or c.date_utc) else target_date
            emp_id = c.employee_id.id if c.employee_id else None
            if not emp_id:
                continue
            key = (emp_id, day)
            groups.setdefault(key, []).append(c)

        for (emp_id, day), items in groups.items():
            # Sort by datetime
            items_sorted = sorted(items, key=lambda x: (x.date_local or x.date_utc or date_start))
            # Build a simplified "raw" view for reuse of filtering logic
            enriched = []
            for c in items_sorted:
                dt = c.date_local or c.date_utc
                if not dt:
                    continue
                job_raw = c.job_number
                token = _normalize_job_number_token(job_raw)
                # Track codes observed on clockings; we'll mark as unmapped later if no project picked them up
                if token:
                    # If this token is not present in any project_job_map, it may remain unmapped
                    if not any(token in codes for codes in project_job_map.values()):
                        project_code_stats['unmapped'].add(token)
                has_poi = any(True for _ in [1] if _record_matches_poi(c, set()))  # placeholder; per-project below
                enriched.append({'clock': c, 'dt': dt, 'type': c.type, 'token': token, 'has_poi': has_poi})
            if not enriched:
                continue

            # For each project, decide if these clockings should be linked based on
            # per-day token/POI logic. A clocking can only be linked to one project;
            # if multiple projects match, prefer the one whose code matches the
            # clocking.project_code if available.
            for proj_id, job_codes in project_job_map.items():
                poi_ids = project_poi_map.get(proj_id, set())
                if not (job_codes or poi_ids):
                    continue

                start_types = getattr(self.env['geodynamics.clocking'], 'ACTIVITY_START_TYPES', set())
                end_types = getattr(self.env['geodynamics.clocking'], 'ACTIVITY_END_TYPES', set())
                # Fallback if ACTIVITY_* not defined on model; use handler defaults if available
                try:
                    from .gdhandler import GeodynamicsHandler
                    handler = GeodynamicsHandler(None, None, None, self.env)
                    start_types = getattr(handler, 'ACTIVITY_START_TYPES', start_types)
                    end_types = getattr(handler, 'ACTIVITY_END_TYPES', end_types)
                except Exception:
                    handler = None

                # Per-day selection flags
                accepted_flags = [False] * len(enriched)
                day_pending_indices = []
                last_valid_token = None
                current_day = None
                day_has_provider = False

                def flush_day_pending():
                    nonlocal day_pending_indices, day_has_provider
                    if not day_pending_indices:
                        return
                    if day_has_provider:
                        for idx in day_pending_indices:
                            accepted_flags[idx] = True
                    day_pending_indices = []
                    day_has_provider = False

                for idx, item in enumerate(enriched):
                    dt = item['dt']
                    day_local = dt.date()
                    if day_local != current_day:
                        flush_day_pending()
                        current_day = day_local
                        last_valid_token = None

                    if item['type'] in start_types:
                        token_ok = (item.get('token') in job_codes) if item.get('token') else False
                        poi_ok = _record_matches_poi(item['clock'], poi_ids)
                        if token_ok:
                            last_valid_token = item['token']
                        if token_ok or poi_ok:
                            accepted_flags[idx] = True
                            day_has_provider = True
                            for p_idx in day_pending_indices:
                                accepted_flags[p_idx] = True
                            day_pending_indices = []
                        else:
                            if last_valid_token is not None:
                                accepted_flags[idx] = True
                            else:
                                day_pending_indices.append(idx)
                flush_day_pending()

                # Link accepted clockings to project if not already linked
                for idx, item in enumerate(enriched):
                    if not accepted_flags[idx]:
                        continue
                    clock = item['clock']
                    if clock.project_id and clock.project_id.id != proj_id:
                        # If already linked to another project, keep existing link
                        continue
                    clock.write({'project_id': proj_id})

        # Consolidation: if any clocking in the same employee/day group has a project assigned,
        # propagate that project to other clockings in the same group (do not overwrite existing projects).
        try:
            for (emp_id, day), items in groups.items():
                try:
                    proj_counts = {}
                    for c in items:
                        pid = c.project_id.id if c.project_id else None
                        if pid:
                            proj_counts[pid] = proj_counts.get(pid, 0) + 1
                    if not proj_counts:
                        continue
                    # choose most common project among assigned ones
                    chosen_pid = max(proj_counts.items(), key=lambda x: x[1])[0]
                    for c in items:
                        if not getattr(c, 'project_id', False):
                            try:
                                c.write({'project_id': chosen_pid})
                            except Exception:
                                _logger.exception('Failed to propagate project %s to clocking %s', chosen_pid, c.id)
                    _logger.info('Propagated project %s to emp=%s for day=%s (%d clockings)', chosen_pid, emp_id, day, len(items))
                except Exception:
                    _logger.exception('Error while consolidating project assignment for emp=%s day=%s', emp_id, day)
        except Exception:
            _logger.exception('Failed during per-day project consolidation')

        # Fallback: for any employee/day group that still has no project assigned on that day,
        # try to inherit the project from the previous day for the same employee.
        try:
            for (emp_id, day), items in groups.items():
                # If any item already has a project, skip
                if any(getattr(c, 'project_id', False) for c in items):
                    continue
                try:
                    prev_day = (day - timedelta(days=1)) if hasattr(day, 'day') else None
                    if not prev_day:
                        continue
                    prev_start = datetime.combine(prev_day, datetime.min.time())
                    prev_end = datetime.combine(prev_day, datetime.max.time())
                    prev_clockings = Clocking.search([
                        ('employee_id', '=', emp_id),
                        ('date_local', '>=', prev_start),
                        ('date_local', '<=', prev_end),
                        ('project_id', '!=', False)
                    ], limit=5)
                    if not prev_clockings:
                        _logger.debug('No previous day project found for emp=%s day=%s', emp_id, day)
                        continue
                    # Pick the most common project_id among previous clockings (or first)
                    proj_counts = {}
                    for pc in prev_clockings:
                        pid = pc.project_id.id if pc.project_id else None
                        if not pid:
                            continue
                        proj_counts[pid] = proj_counts.get(pid, 0) + 1
                    if not proj_counts:
                        continue
                    chosen_pid = max(proj_counts.items(), key=lambda x: x[1])[0]
                    # Assign chosen project to all items in the current day that have no project
                    for c in items:
                        if not getattr(c, 'project_id', False):
                            try:
                                c.write({'project_id': chosen_pid})
                            except Exception:
                                _logger.exception('Failed to assign fallback project %s to clocking %s', chosen_pid, c.id)
                    _logger.info('Fallback assigned project %s to emp=%s for day=%s based on previous day', chosen_pid, emp_id, day)
                except Exception:
                    _logger.exception('Error while applying previous-day fallback for emp=%s day=%s', emp_id, day)
        except Exception:
            _logger.exception('Failed during previous-day fallback project assignment')

        # Log summary of project code mappings
        try:
            mapped_summary = {
                code: sorted(list(pids)) for code, pids in project_code_stats['mapped'].items()
            }
            unmapped_codes = sorted(list(project_code_stats['unmapped'] - set(mapped_summary.keys())))
            _logger.info(
                'Project assignment summary for %s: mapped_codes=%s, unmapped_codes=%s',
                target_date,
                mapped_summary,
                unmapped_codes,
            )
        except Exception:
            _logger.exception('Failed to log project code mapping summary for %s', target_date)

        _logger.info('Project assignment: processed %d clockings for %s', len(clockings), target_date)

    @api.model
    def fetch_clockings_by_date(self, target_date):
        """Fetch clockings for a specific date and persist them in geodynamics.clocking.

        Args:
            target_date: date object or datetime object for which to fetch clockings

        Returns:
            bool: True if successful, False otherwise
        """
        login, password, company = self._get_credentials()
        if not login or not password or not company:
            _logger.warning('Geodynamics credentials not configured, skipping fetch_clockings_by_date')
            return False

        # Construct handler (the GeodynamicsHandler class lives in geodynamics.models.gdhandler)
        from .gdhandler import GeodynamicsHandler

        handler = GeodynamicsHandler(login, password, company, self.env)

        # Normalize target_date to date object
        if isinstance(target_date, datetime):
            target_date = target_date.date()

        # Date range: from 00:00:00 to 23:59:59 of target date
        from_dt = datetime.combine(target_date, datetime.min.time())
        to_dt = datetime.combine(target_date, datetime.max.time()).replace(microsecond=0)

        _logger.info('Fetching geodynamics clockings for %s (from %s to %s)', target_date, from_dt, to_dt)

        try:
            res = handler.getClockingsByDateRange(from_dt, to_dt, includeClockingsWithoutUser=False, raise_on_error=False)
        except Exception as e:
            _logger.exception('Error while fetching clockings for %s: %s', target_date, e)
            return False

        if not res or 'Error' in res:
            _logger.warning('Geodynamics fetch returned error for %s: %s', target_date, res)
            return False

        records = res.get('Data') or res.get('data') or res.get('Data', [])
        if not records:
            _logger.info('No clocking records returned for %s', target_date)
            return True

        # Normalize to list
        records_list = records if isinstance(records, list) else [records]

        # Group by (User.Id, date) using handler._extract_clock_dt to determine datetime
        groups = {}
        for rec in records_list:
            try:
                user_id = None
                if isinstance(rec, dict):
                    user_id = rec.get('User', {}) and rec.get('User', {}).get('Id')
                # Prefer DateTimeLocal for grouping (group by local day). If missing, fall back to handler._extract_clock_dt
                dt = None
                day = None
                if isinstance(rec, dict):
                    dt_local_str = rec.get('DateTimeLocal')
                    if dt_local_str:
                        try:
                            # try ISO parsing, accept 'Z' or offset; don't convert tz -> keep local date
                            dt_try = datetime.fromisoformat(dt_local_str.replace('Z', '+00:00'))
                            # If timezone-aware, convert to that timezone's local date by not converting to UTC
                            if dt_try.tzinfo:
                                # convert to UTC then take date in UTC as fallback
                                dt = dt_try.astimezone(pytz.UTC).replace(tzinfo=None)
                                day = dt.date()
                            else:
                                dt = dt_try
                                day = dt.date()
                        except Exception:
                            try:
                                dt_try = datetime.strptime(dt_local_str[:19], '%Y-%m-%dT%H:%M:%S')
                                dt = dt_try
                                day = dt.date()
                            except Exception:
                                dt = None
                                day = None
                if day is None:
                    try:
                        dt = handler._extract_clock_dt(rec)
                        day = dt.date() if dt else None
                    except Exception:
                        day = None
                # Only group records that have a valid user_id (require grouping by User->Id)
                if not user_id:
                    _logger.debug('Skipping clocking without User.Id for grouping: %s', rec)
                    continue
                key = (user_id, day)
                groups.setdefault(key, []).append({'rec': rec, 'dt': dt})
            except Exception:
                _logger.exception('Error while grouping clocking record: %s', rec)

        # For each group, find Type==12 records and mark earliest and latest as woon_werk
        movement_cache = {}
        break_updates = 0
        for key, items in groups.items():
            try:
                # sort by dt (None values go last)
                items_sorted = sorted(items, key=lambda x: (x['dt'] is None, x['dt']))
                type12_items = [it for it in items_sorted if isinstance(it['rec'], dict) and it['rec'].get('Type') == 12]
                if type12_items:
                    # Filter type12_items to only include vehicles with allowed codes
                    allowed_type12_items = []
                    for it in type12_items:
                        rec = it['rec']
                        vehicle_data = rec.get('Vehicle')
                        if self._is_vehicle_allowed_for_woon_werk(vehicle_data):
                            allowed_type12_items.append(it)

                    # Only mark woon_werk if there are allowed vehicles
                    if allowed_type12_items:
                        # mark first and last from allowed vehicles
                        first = allowed_type12_items[0]['rec']
                        last = allowed_type12_items[-1]['rec']
                        try:
                            first['woon_werk'] = True
                        except Exception:
                            _logger.debug('Could not set woon_werk on first record: %s', first)
                        try:
                            last['woon_werk'] = True
                        except Exception:
                            _logger.debug('Could not set woon_werk on last record: %s', last)
                # compute activity duration for any Start types (handler.ACTIVITY_START_TYPES):
                # duration ends at the next event whose type is in ACTIVITY_END_TYPES or ACTIVITY_START_TYPES
                start_types = getattr(handler, 'ACTIVITY_START_TYPES', set())
                end_types = getattr(handler, 'ACTIVITY_END_TYPES', set())
                for idx, item in enumerate(items_sorted):
                    rec = item['rec']
                    dt = item['dt']
                    if not isinstance(rec, dict) or rec.get('Type') not in start_types or not dt:
                        continue
                    end_dt = None
                    for j in range(idx + 1, len(items_sorted)):
                        nxt = items_sorted[j]
                        nxt_rec = nxt['rec']
                        nxt_dt = nxt['dt']
                        if not nxt_dt or not isinstance(nxt_rec, dict):
                            continue
                        nxt_type = nxt_rec.get('Type')
                        if (nxt_type in end_types) or (nxt_type in start_types):
                            end_dt = nxt_dt
                            break
                    if end_dt and end_dt > dt:
                        delta = end_dt - dt
                        minutes = int(delta.total_seconds() // 60)
                        if minutes > 0:
                            hours = round(minutes / 60.0, 2)
                            try:
                                rec['movement_time_minutes'] = minutes
                                rec['movement_time_hours'] = hours
                                # Also set stop datetime for the activity (will be persisted to stop_date_utc/stop_date_local)
                                rec['Stop'] = end_dt.isoformat() if isinstance(end_dt, datetime) else end_dt
                                # Derive StopDateTimeLocal assuming end_dt is in local time (same as DateTimeLocal)
                                rec['StopDateTimeLocal'] = end_dt.isoformat() if isinstance(end_dt, datetime) else end_dt
                            except Exception as e:
                                _logger.debug('Could not set activity_time/stop on rec: %s, error: %s', rec, e)

                # compute movement_distance for Movement Drive (Type==12) using location status API
                _, group_day = key
                self._compute_movement_distance_for_type12(handler, type12_items, group_day, movement_cache, is_raw_records=True)
                break_updates += self._compute_break_time_for_type5(items_sorted, is_raw_records=True)
            except Exception:
                _logger.exception('Error while computing woon_werk/activity time for group %s', key)

        # Persist all records
        count = 0
        for it in records_list:
            rec = it
            try:
                self.env['geodynamics.clocking'].create_from_raw(rec)
                count += 1
            except Exception:
                _logger.exception('Failed to persist clocking record: %s', rec)

        _logger.info('Persisted %d clocking records for %s', count, target_date)

        # After persisting, assign projects on clockings for this date
        try:
            self._assign_projects_for_date(target_date)
        except Exception:
            _logger.exception('Failed to assign projects for %s', target_date)

        # For any project that received clockings on this date, trigger its fetchClockings
        try:
            Clocking = self.env['geodynamics.clocking'].sudo()
            date_start = datetime.combine(target_date, datetime.min.time())
            date_end = datetime.combine(target_date, datetime.max.time())
            assigned_clockings = Clocking.search([
                ('date_local', '>=', date_start),
                ('date_local', '<=', date_end),
                ('project_id', '!=', False)
            ])
            project_ids = set(assigned_clockings.mapped('project_id.id'))
            if project_ids:
                Project = self.env['project.project'].sudo()
                projects = Project.browse(list(project_ids))
                for proj in projects:
                    try:
                        _logger.info('Triggering fetchClockings for project %s to update timesheets', proj.id)
                        # Call fetchClockings to update timesheets based on newly assigned clockings
                        proj.fetchClockings()
                    except Exception as e:
                        _logger.exception('Failed to update timesheets for project %s: %s', proj.id, e)
        except Exception:
            _logger.exception('Failed while triggering project timesheet updates for %s', target_date)

        # Check for time discrepancies after syncing
        self._check_time_discrepancies(target_date)

        return True

    @api.model
    def _check_time_discrepancies(self, check_date):
        """Check for time discrepancies between employees working on same project on same day.

        Args:
            check_date: date object to check
        """
        if isinstance(check_date, datetime):
            check_date = check_date.date()

        # Get all clockings for this date with project codes
        date_start = datetime.combine(check_date, datetime.min.time())
        date_end = datetime.combine(check_date, datetime.max.time())

        clockings = self.env['geodynamics.clocking'].search([
            ('date_local', '>=', date_start),
            ('date_local', '<=', date_end),
            ('project_code', '!=', False),
            ('movement_time_minutes', '>', 0)
        ])

        if not clockings:
            _logger.debug('No clockings with project codes found for %s', check_date)
            return

        # Group by project_code
        projects = {}
        for clocking in clockings:
            project_code = clocking.project_code
            if project_code not in projects:
                projects[project_code] = []
            projects[project_code].append(clocking)

        # Check each project
        error_model = self.env['geodynamics.clocking.possible.error']

        for project_code, project_clockings in projects.items():
            # Group by employee
            employee_times = {}
            employee_names = {}

            for clocking in project_clockings:
                employee_id = clocking.employee_id.id if clocking.employee_id else clocking.user_id_geodynamics
                if not employee_id:
                    continue

                employee_name = clocking.employee_id.name if clocking.employee_id else f"User {clocking.user_id_geodynamics}"

                if employee_id not in employee_times:
                    employee_times[employee_id] = 0
                    employee_names[employee_id] = employee_name

                # Sum total minutes for this employee
                minutes = clocking.movement_time_minutes or 0
                employee_times[employee_id] += minutes

            # Check if there are at least 2 employees
            if len(employee_times) < 2:
                # Reset need_to_check flag for single employee projects
                for clocking in project_clockings:
                    clocking.write({'need_to_check': False})
                continue

            # Calculate time differences
            times = list(employee_times.values())
            max_time = max(times)
            min_time = min(times)

            # Skip if max_time is 0 (avoid division by zero)
            if max_time == 0:
                continue

            # Calculate percentage difference
            time_diff_percent = ((max_time - min_time) / max_time) * 100

            if time_diff_percent > 5:  # More than 5% difference
                _logger.warning('Time discrepancy detected for project %s on %s: %.2f%% difference',
                               project_code, check_date, time_diff_percent)

                # Mark all clockings as need_to_check
                for clocking in project_clockings:
                    clocking.write({'need_to_check': True})

                # Build employee details text
                employee_details_lines = []
                for emp_id, total_minutes in employee_times.items():
                    emp_name = employee_names[emp_id]
                    hours = total_minutes / 60.0
                    employee_details_lines.append(f"{emp_name}: {hours:.2f} uur ({total_minutes} minuten)")

                employee_details = '\n'.join(employee_details_lines)

                # Get IDs from list of records
                clocking_ids = [clocking.id for clocking in project_clockings]

                # Check if error record already exists
                existing_error = error_model.search([
                    ('error_date', '=', check_date),
                    ('project_code', '=', project_code)
                ], limit=1)

                error_vals = {
                    'error_date': check_date,
                    'project_code': project_code,
                    'employee_details': employee_details,
                    'clocking_ids': [(6, 0, clocking_ids)],
                }

                if existing_error:
                    # Update existing error record
                    existing_error.write(error_vals)
                    _logger.info('Updated existing error record for %s on %s', project_code, check_date)
                else:
                    # Create new error record
                    error_model.create(error_vals)
                    _logger.info('Created error record for %s on %s with %d employees',
                                project_code, check_date, len(employee_times))
            else:
                # No significant discrepancy, reset need_to_check flag
                for clocking in project_clockings:
                    clocking.write({'need_to_check': False})

                # Remove error record if it exists
                existing_error = error_model.search([
                    ('error_date', '=', check_date),
                    ('project_code', '=', project_code)
                ], limit=1)
                if existing_error:
                    existing_error.unlink()
                    _logger.info('Removed error record for %s on %s (discrepancy resolved)',
                                project_code, check_date)

    @api.model
    def cron_fetch_yesterday_clockings(self):
        """Cron wrapper to fetch yesterday's clockings and persist them in geodynamics.clocking."""
        # Calculate yesterday's date
        today = datetime.now()
        yesterday = today.date() - timedelta(days=1)

        _logger.info('Cron: fetching geodynamics clockings for yesterday: %s', yesterday)

        return self.fetch_clockings_by_date(yesterday)

    @api.model
    def cron_auto_sync_planning(self):
        """Cron: auto-export task plannings that do not yet exist in Geodynamics.

        Runs only when 'Planning Sync' is enabled in Settings. Selects tasks that
        have start/deadline dates and at least one linked employee with a
        Geodynamics ID, but no Geodynamics planning records yet, and pushes their
        planning to Geodynamics. This mirrors the manual 'Plan to Geodynamics'
        action so users don't have to trigger it on each task.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('geodynamics.auto_sync_planning', 'False').lower() not in ('true', '1', 'yes'):
            return

        login, password, company = self._get_credentials()
        if not (login and password and company):
            _logger.warning('[Geodynamics] Auto planning sync skipped: credentials missing')
            return

        from .gdhandler import GeodynamicsHandler
        handler = GeodynamicsHandler(login, password, company, self.env)

        now = fields.Datetime.now()
        tasks = self.env['project.task'].sudo().search([
            ('planned_date_start', '!=', False),
            ('date_deadline', '!=', False),
            ('date_deadline', '>=', now),
            ('df_gd_planning_ids', '=', False),
        ])

        pushed = 0
        skipped = 0
        for task in tasks:
            # Skip tasks that are already in a completion stage
            if task.stage_id and task.stage_id.df_is_completion_stage:
                skipped += 1
                continue
            # Need at least one employee with a Geodynamics ID to plan
            if not task.df_employees_with_geodynamics_ids:
                skipped += 1
                continue
            try:
                # Per-task savepoint so a single failure doesn't roll back the whole run
                with self.env.cr.savepoint():
                    handler.createPlanningByTaskWn(task)
                pushed += 1
            except Exception as e:
                skipped += 1
                _logger.exception('[Geodynamics] Auto planning sync failed for task %s: %s', task.id, e)

        _logger.info('[Geodynamics] Auto planning sync: %d tasks pushed, %d skipped', pushed, skipped)

    @api.model
    def backfill_movement_for_date_range(self, start_date, end_date=None):
        """Backfill woon_werk and activity time fields for existing geodynamics.clocking records.

        start_date: string 'YYYY-MM-DD' or date/datetime
        end_date: optional string 'YYYY-MM-DD' (inclusive). If None, uses start_date.
        The method groups records by (user id, local date) and applies the same logic as the cron:
          - mark earliest and latest Type==12 as woon_werk
          - for each Start (in ACTIVITY_START_TYPES), compute duration until next End (in ACTIVITY_END_TYPES) or next Start
        Returns the number of records updated.
        """
        # normalize inputs
        from datetime import datetime as _dt
        if isinstance(start_date, str):
            sd = _dt.strptime(start_date, '%Y-%m-%d').date()
        elif hasattr(start_date, 'date'):
            sd = start_date.date() if isinstance(start_date, _dt) else start_date
        else:
            sd = start_date
        if end_date is None:
            ed = sd
        elif isinstance(end_date, str):
            ed = _dt.strptime(end_date, '%Y-%m-%d').date()
        elif hasattr(end_date, 'date'):
            ed = end_date.date() if isinstance(end_date, _dt) else end_date
        else:
            ed = end_date

        # build datetime range
        start_dt = _dt.combine(sd, _dt.min.time())
        end_dt = _dt.combine(ed, _dt.max.time())

        records = self.env['geodynamics.clocking'].search([('date_local', '>=', start_dt.strftime('%Y-%m-%d %H:%M:%S')), ('date_local', '<=', end_dt.strftime('%Y-%m-%d %H:%M:%S'))])
        if not records:
            _logger.info('Backfill: no geodynamics.clocking records found between %s and %s', start_dt, end_dt)
            return 0

        # group by user id and date
        groups = {}
        for r in records:
            user_id = (r.user or {}).get('Id') if r.user else None
            if not user_id:
                continue
            # prefer date_local when present
            dt = r.date_local or r.date_utc
            if not dt:
                continue
            day = dt.date()
            key = (user_id, day)
            groups.setdefault(key, []).append(r)

        updated = 0
        movement_cache = {}
        for key, items in groups.items():
            # sort by datetime
            items_sorted = sorted(items, key=lambda x: (x.date_local is None, x.date_local))
            # mark woon_werk on first/last Type==12
            type12 = [it for it in items_sorted if it.type == 12]
            if type12:
                # Filter type12 to only include vehicles with allowed codes
                allowed_type12 = []
                for it in type12:
                    vehicle_data = it.vehicle if isinstance(it.vehicle, dict) else None
                    # Try raw_payload as backup
                    if not vehicle_data and isinstance(it.raw_payload, dict):
                        vehicle_data = it.raw_payload.get('Vehicle')
                    if self._is_vehicle_allowed_for_woon_werk(vehicle_data):
                        allowed_type12.append(it)

                # Only mark woon_werk if there are allowed vehicles
                if allowed_type12:
                    try:
                        allowed_type12[0].write({'woon_werk': True})
                        updated += 1
                    except Exception:
                        _logger.exception('Failed to write woon_werk on %s', allowed_type12[0].id)
                    try:
                        allowed_type12[-1].write({'woon_werk': True})
                        updated += 1
                    except Exception:
                        _logger.exception('Failed to write woon_werk on %s', allowed_type12[-1].id)

            # compute activity durations similar to cron: for any Start (in ACTIVITY_START_TYPES)
            from .gdhandler import GeodynamicsHandler
            handler = GeodynamicsHandler(None, None, None, self.env)
            start_types = getattr(handler, 'ACTIVITY_START_TYPES', set())
            end_types = getattr(handler, 'ACTIVITY_END_TYPES', set())
            for idx, rec in enumerate(items_sorted):
                if rec.type not in start_types or not rec.date_local:
                    continue
                end_dt_activity = None
                for nxt in items_sorted[idx + 1:]:
                    if not nxt.date_local:
                        continue
                    nxt_type = nxt.type
                    if (nxt_type in end_types) or (nxt_type in start_types):
                        end_dt_activity = nxt.date_local
                        break
                if end_dt_activity and end_dt_activity > rec.date_local:
                    delta = end_dt_activity - rec.date_local
                    minutes = int(delta.total_seconds() // 60)
                    if minutes > 0:
                        hours = round(minutes / 60.0, 2)
                        try:
                            # Write activity times and stop datetime
                            rec.write({
                                'movement_time_minutes': minutes,
                                'movement_time_hours': hours,
                                'stop_date_local': end_dt_activity,
                                'stop_date_utc': end_dt_activity  # assuming end_dt_activity is in local time, convert if needed
                            })
                            updated += 1
                        except Exception:
                            _logger.exception('Failed to write activity times and stop dates on %s', rec.id)

            # compute movement_distance for Movement Drive (Type==12) for this day per vehicle
            group_day = (items_sorted[0].date_local or items_sorted[0].date_utc).date() if items_sorted and (items_sorted[0].date_local or items_sorted[0].date_utc) else None
            if group_day and type12:
                updated += self._compute_movement_distance_for_type12(handler, type12, group_day, movement_cache, is_raw_records=False)
            if items_sorted:
                updated += self._compute_break_time_for_type5(items_sorted, is_raw_records=False)

        _logger.info('Backfill: updated %d records between %s and %s', updated, start_dt, end_dt)
        return updated

    def _compute_break_time_for_type5(self, items, is_raw_records=True):
        """Annotate break durations (pause_hours) captured by Type 5 (Start Break).

        Args:
            items: list of raw dict wrappers ({'rec','dt'}) or geodynamics.clocking records
            is_raw_records (bool): True when items are raw fetch data
        Returns:
            int: number of records annotated
        """
        if not items:
            return 0
        updated = 0
        break_start_payload = None
        break_start_dt = None

        def _get_payload(item):
            return item.get('rec') if is_raw_records else item

        def _get_dt(item):
            if is_raw_records:
                return item.get('dt') if isinstance(item, dict) else None
            return item.date_local or item.date_utc

        def _is_break_start(payload):
            if not payload:
                return False
            if isinstance(payload, dict):
                rec_type = payload.get('Type')
                label = (payload.get('Label') or payload.get('TypeLabel') or '')
            else:
                rec_type = payload.type
                label = payload.type_label or ''
            return rec_type == 5 or label.strip().lower() == 'start break'

        items_sorted = sorted(items, key=lambda itm: (_get_dt(itm) is None, _get_dt(itm)))
        for idx, item in enumerate(items_sorted):
            payload = _get_payload(item)
            dt = _get_dt(item)
            if not payload or not dt:
                continue
            if _is_break_start(payload):
                break_start_payload = payload
                break_start_dt = dt
                continue
            if break_start_payload and break_start_dt:
                payload_type = payload.get('Type') if isinstance(payload, dict) else payload.type
                stop_dt = None
                if payload_type != 5 and dt > break_start_dt:
                    stop_dt = dt
                elif idx == len(items_sorted) - 1:
                    # reached end of day while still type 5 -> cannot compute reliable stop
                    break_start_payload = None
                    break_start_dt = None
                    continue
                if stop_dt:
                    seconds = (stop_dt - break_start_dt).total_seconds()
                    if seconds > 0:
                        hours = round(seconds / 3600.0, 2)
                        try:
                            if is_raw_records:
                                break_start_payload['pause_hours'] = hours
                            else:
                                break_start_payload.write({'pause_hours': hours})
                            updated += 1
                        except Exception:
                            rec_id = break_start_payload.get('Id') if isinstance(break_start_payload, dict) else break_start_payload.id
                            _logger.debug('Unable to persist pause_hours on record %s', rec_id)
                    break_start_payload = None
                    break_start_dt = None

        # If day ends while break is still open, we cannot compute duration reliably
        return updated
