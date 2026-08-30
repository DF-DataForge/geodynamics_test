# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime
import logging
import pytz

_logger = logging.getLogger(__name__)


class GeodynamicsClocking(models.Model):
    _name = 'geodynamics.clocking'
    _description = 'Geodynamics Clocking Record'
    _order = 'date_utc desc'
    _rec_name = 'external_id'

    external_id = fields.Char(string='External Id', index=True, required=True)
    date_local = fields.Datetime(string='DateTimeLocal', index=True)
    date_utc = fields.Datetime(string='DateTimeUtc', index=True)
    stop_date_local = fields.Datetime(string='Stop DateTimeLocal', index=True)
    stop_date_utc = fields.Datetime(string='Stop DateTimeUtc', index=True)
    type = fields.Integer(string='Type')
    type_label = fields.Char(string='TypeLabel')
    job_number = fields.Char(string='JobNumber')
    description = fields.Text(string='Description')
    note = fields.Text(string='Note')
    is_manual = fields.Boolean(string='IsManual')
    woon_werk = fields.Boolean(string='Woon-Werk')
    # activity durations computed in cron: minutes and hours (was Movement Time)
    movement_time_minutes = fields.Integer(string='Activity Time (minutes)')
    movement_time_hours = fields.Float(string='Activity Time (hours)')
    # distance captured for Movement Drive activity (per-day, from location status)
    movement_distance = fields.Float(string='Movement Distance')
    pause_hours = fields.Float(string='Break Time (hours)')
    absence_code = fields.Char(string='AbsenceCode')
    external_code = fields.Char(string='ExternalCode')
    external_type = fields.Char(string='ExternalType')

    location = fields.Json(string='Location')
    pois = fields.Json(string='Pois')
    user = fields.Json(string='User')
    # store the external Geodynamics user id (User->Id) as a simple searchable field
    user_id_geodynamics = fields.Char(string='UserId', index=True)
    vehicle = fields.Json(string='Vehicle')
    # store the vehicle code (Vehicle->Code) as a simple searchable field
    vehicle_code = fields.Char(string='Vehicle Code', index=True)
    raw_payload = fields.Json(string='Raw Payload')

    project_id = fields.Many2one('project.project', string='Project', ondelete='set null')
    employee_id = fields.Many2one('hr.employee', string='Employee', ondelete='set null')

    # Link to timesheet line
    timesheet_line_id = fields.Many2one(
        'account.analytic.line',
        string='Timesheet Line',
        ondelete='set null',
        index=True,
        help='Link to the timesheet line (account.analytic.line) this clocking is associated with'
    )

    # Project code extracted from JobNumber (e.g., S00651)
    project_code = fields.Char(string='Project Code', index=True, compute='_compute_project_code', store=True)
    # Flag to indicate data needs checking due to time discrepancy
    need_to_check = fields.Boolean(string='Need to Check', default=False, index=True)

    _sql_constraints = [
        ('geodynamics_clocking_external_uniq', 'UNIQUE(external_id)', 'Clocking external id must be unique.')
    ]

    @api.depends('job_number')
    def _compute_project_code(self):
        """Extract project code (Sxxxxx pattern) from JobNumber."""
        import re
        for rec in self:
            if rec.job_number:
                # Pattern: S followed by 5 digits (e.g., S00651)
                match = re.search(r'(S\d{5})', rec.job_number.upper())
                if match:
                    rec.project_code = match.group(1)
                else:
                    rec.project_code = False
            else:
                rec.project_code = False

    @api.model
    def _parse_iso_dt(self, s, assume_utc_if_naive=False):
        """Parse incoming ISO-like datetime strings into a naive datetime.

        - Accepts values that are already datetime objects.
        - Accepts ISO strings like '2025-10-22T08:00:00' or with timezone '2025-10-22T08:00:00+02:00' or '...Z'.
        - If the string includes timezone info, convert to UTC and return a naive UTC datetime.
        - If the string is naive (no tz info):
            - if assume_utc_if_naive is True, treat it as UTC and return naive UTC datetime;
            - otherwise return the naive datetime as-is (useful for DateTimeLocal which is local time).
        Returns False if parsing fails.
        """
        if not s:
            return False
        if isinstance(s, datetime):
            dt = s
            # If it's timezone-aware, normalize to UTC and return naive UTC
            if getattr(dt, 'tzinfo', None):
                try:
                    dt = dt.astimezone(pytz.UTC).replace(tzinfo=None)
                except Exception:
                    dt = dt.replace(tzinfo=None)
            else:
                # naive datetime
                if assume_utc_if_naive:
                    # treat as UTC (just return as-is since storage uses naive UTC)
                    pass
            return dt
        if not isinstance(s, str):
            return False
        s = s.strip()
        if s == '':
            return False
        # Try ISO parsing with fromisoformat (py3.7+). Handle trailing Z.
        try:
            iso_candidate = s.replace('Z', '+00:00')
            dt = datetime.fromisoformat(iso_candidate)
        except Exception:
            # Fallback formats
            dt = None
            for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f'):
                try:
                    dt = datetime.strptime(s[:26], fmt)
                    break
                except Exception:
                    continue
        if dt is None:
            _logger.debug('Failed to parse datetime (all attempts) for: %s', s)
            return False
        # If timezone-aware, convert to UTC and make naive
        if getattr(dt, 'tzinfo', None):
            try:
                dt_utc = dt.astimezone(pytz.UTC).replace(tzinfo=None)
                return dt_utc
            except Exception:
                return dt.replace(tzinfo=None)
        # dt is naive
        if assume_utc_if_naive:
            # treat naive as UTC (no conversion needed)
            return dt
        # otherwise return naive dt as-is (local time representation)
        return dt

    @api.model
    def _parse_bool(self, val):
        if isinstance(val, bool):
            return val
        if val is None:
            return False
        try:
            s = str(val).strip().lower()
            return s in ('1', 'true', 'yes', 'y', 't')
        except Exception:
            return False

    @api.model
    def create_from_raw(self, raw, project=None, employee=None):
        """Create or update a geodynamics.clocking record from raw dict.

        raw: dict as provided by the external API
        project: optional project.record or id to link
        employee: optional hr.employee record or id to link
        """
        if not isinstance(raw, dict):
            raise ValueError('raw must be a dict')
        ext_id = raw.get('Id') or raw.get('id')
        if not ext_id:
            ext_id = f"{raw.get('User', {}).get('Id')}_{raw.get('DateTimeUtc') or raw.get('DateTimeLocal')}"
        # prepare woon_werk and movement_time values carefully (preserve zeros and parse strings)
        woon_val = raw.get('woon_werk') if 'woon_werk' in raw else (raw.get('WoonWerk') if 'WoonWerk' in raw else None)
        mt_min = raw.get('movement_time_minutes') if 'movement_time_minutes' in raw else (raw.get('MovementTimeMinutes') if 'MovementTimeMinutes' in raw else None)
        mt_hrs = raw.get('movement_time_hours') if 'movement_time_hours' in raw else (raw.get('MovementTimeHours') if 'MovementTimeHours' in raw else None)
        mdist = raw.get('movement_distance') if 'movement_distance' in raw else (raw.get('MovementDistance') if 'MovementDistance' in raw else None)
        pause_hours = raw.get('pause_hours') if 'pause_hours' in raw else (raw.get('PauseHours') if 'PauseHours' in raw else None)

        vals = {
            'external_id': ext_id,
            # DateTimeLocal: keep as local naive datetime when no tz is provided
            'date_local': self._parse_iso_dt(raw.get('DateTimeLocal'), assume_utc_if_naive=False),
            # DateTimeUtc: treat naive strings as UTC (store as naive UTC datetime)
            'date_utc': self._parse_iso_dt(raw.get('DateTimeUtc'), assume_utc_if_naive=True),
            # Stop datetime fields for start-type activities
            'stop_date_local': self._parse_iso_dt(raw.get('StopDateTimeLocal'), assume_utc_if_naive=False) or False,
            'stop_date_utc': self._parse_iso_dt(raw.get('StopDateTimeUtc') or raw.get('Stop'), assume_utc_if_naive=True) or False,
            'type': raw.get('Type'),
            'type_label': raw.get('TypeLabel'),
            'job_number': (raw.get('JobNumber') or '').strip() if raw.get('JobNumber') else raw.get('JobNumber'),
            'description': raw.get('Description'),
            'note': raw.get('Note'),
            'is_manual': bool(raw.get('IsManual')),
            # allow external code to set woon_werk flag (cron will annotate this key)
            'woon_werk': self._parse_bool(woon_val),
            # allow cron to annotate activity durations (preserve zero values)
            'movement_time_minutes': (int(mt_min) if mt_min is not None and mt_min != '' else None),
            'movement_time_hours': (float(mt_hrs) if mt_hrs is not None and mt_hrs != '' else None),
            'movement_distance': (float(mdist) if mdist is not None and mdist != '' else None),
            'pause_hours': (float(pause_hours) if pause_hours is not None and pause_hours != '' else None),
            'absence_code': raw.get('AbsenceCode'),
            'external_code': raw.get('ExternalCode'),
            'external_type': raw.get('ExternalType'),
            'location': raw.get('Location'),
            'pois': raw.get('Pois'),
            'user': raw.get('User'),
            'vehicle': raw.get('Vehicle'),
            'raw_payload': raw,
        }
        if project:
            vals['project_id'] = project.id if hasattr(project, 'id') else project
        # Auto-link employee if not provided and User.Id present in payload (only here)
        if employee:
            vals['employee_id'] = employee.id if hasattr(employee, 'id') else employee
        else:
            user_id = raw.get('User', {}) and raw.get('User', {}).get('Id')
            if user_id:
                emp = self._find_employee_by_userid(user_id)
                if emp:
                    vals['employee_id'] = emp.id
        # Always store external user id in dedicated field for easier queries
        vals['user_id_geodynamics'] = raw.get('User', {}) and raw.get('User', {}).get('Id')
        # Always store vehicle code in dedicated field for easier queries
        vehicle_data = raw.get('Vehicle')
        if isinstance(vehicle_data, dict):
            vehicle_code = vehicle_data.get('Code') or ''
            vehicle_code = vehicle_code.strip() if vehicle_code else ''
            vals['vehicle_code'] = vehicle_code if vehicle_code else False
        else:
            vals['vehicle_code'] = False

        existing = self.search([('external_id', '=', ext_id)], limit=1)
        if existing:
            existing.write(vals)
            return existing
        else:
            return self.create(vals)

    @api.model
    def _find_employee_by_userid(self, user_id):
        """Return hr.employee record matching df_geodynamics_id == user_id or False."""
        if not user_id:
            return False
        return self.env['hr.employee'].search([('df_geodynamics_id', '=', user_id)], limit=1) or False
