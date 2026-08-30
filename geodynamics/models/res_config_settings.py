# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import fields, models, api
from .gdhandler import GeodynamicsHandler
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
import logging
import traceback

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    df_geodynamics_company = fields.Char(string='Geodynamics company', config_parameter='geodynamics.company')
    df_geodynamics_login = fields.Char(string='Geodynamics username', config_parameter='geodynamics.username')
    df_geodynamics_password = fields.Char(string='Geodynamics password', config_parameter='geodynamics.password')

    df_geodynamics_postcalcsource = fields.Selection(selection=[('timesheet','Timesheetevents'),('postcalculation', 'Postcalculationevents')],string='Bron nacalculatie',required=True,default='postcalculation', config_parameter='geodynamics.postcalcsource')

    df_geodynamics_warning_planning_overlap = fields.Boolean(string='Toon waarschuwing wanneer planningen overlappen', default=False, config_parameter='geodynamics.wapp')

    df_geodynamics_woon_werk_vehicle_codes = fields.Char(
        string='Vehicle Codes voor Woon-Werk',
        help='Lijst van vehicle codes (gescheiden door komma) die gebruikt worden voor woon-werk berekening. Bijvoorbeeld: CODE1,CODE2,CODE3',
        config_parameter='geodynamics.woon_werk_vehicle_codes'
    )

    df_persones_gd_ids = fields.Many2many('hr.employee', string='Personen geodynamics',
                                                            compute='_wn_pers_gd')

    df_plan_directly = fields.Boolean(string='Plan rechtstreeks in naar Geodynamics bij wijzigen taak', config_parameter='geodynamics.plandirectly')

    # Planning visibility
    df_geodynamics_planning_project = fields.Boolean(
        string='Enable planning on project level', default=False,
        config_parameter='geodynamics.planning_project'
    )
    df_geodynamics_planning_task = fields.Boolean(
        string='Enable planning on task level', default=False,
        config_parameter='geodynamics.planning_task'
    )
    # Auto-sync settings
    df_geodynamics_auto_sync_employees = fields.Boolean(
        string='Auto-sync Employees', default=False,
        config_parameter='geodynamics.auto_sync_employees'
    )
    df_geodynamics_auto_sync_fleet = fields.Boolean(
        string='Auto-sync Fleet', default=False,
        config_parameter='geodynamics.auto_sync_fleet'
    )
    df_geodynamics_auto_sync_odometer = fields.Boolean(
        string='Auto-sync Odometer', default=False,
        config_parameter='geodynamics.auto_sync_odometer',
        help='Daily background job that logs the kilometers of each linked vehicle '
             'from Geodynamics into the Odoo fleet odometer.',
    )
    df_geodynamics_odometer_days_back = fields.Integer(
        string='Odometer Initial Days Back', default=30,
        config_parameter='geodynamics.odometer_days_back',
        help='For vehicles without any odometer log yet, how many days of trip data '
             '(location status) to fetch on the first sync.',
    )
    df_geodynamics_auto_sync_leaves = fields.Boolean(
        string='Auto-sync Leaves', default=False,
        config_parameter='geodynamics.auto_sync_leaves'
    )
    df_geodynamics_leave_sync_months_back = fields.Integer(
        string='Leave Sync Months Back', default=1,
        config_parameter='geodynamics.leave_sync_months_back',
        help='How many months in the past the automatic leave sync should fetch leaves.',
    )
    df_geodynamics_leave_sync_months_forward = fields.Integer(
        string='Leave Sync Months Forward', default=11,
        config_parameter='geodynamics.leave_sync_months_forward',
        help='How many months in the future the automatic leave sync should fetch leaves.',
    )
    df_geodynamics_auto_sync_planning = fields.Boolean(
        string='Auto-sync Planning', default=False,
        config_parameter='geodynamics.auto_sync_planning'
    )
    # Tracking settings
    df_geodynamics_enable_tracking = fields.Boolean(
        string='Enable Location Tracking', default=False,
        config_parameter='geodynamics.enable_tracking'
    )
    df_geodynamics_tracking_interval = fields.Selection(
        [('5', '5 minutes'), ('15', '15 minutes'), ('30', '30 minutes'), ('60', '1 hour')],
        string='Tracking Interval', default='15',
        config_parameter='geodynamics.tracking_interval'
    )
    # Clocking sync window
    df_geodynamics_sync_days_back = fields.Integer(
        string='Sync Days Back', default=1,
        config_parameter='geodynamics.sync_days_back',
    )
    # Planning sync from date
    df_geodynamics_planning_from_date = fields.Char(
        string='Planning Sync From Date',
        config_parameter='geodynamics.planning_from_date',
        help='Start date for fetching plannings from Geodynamics (YYYY-MM-DD). If not set, defaults to 90 days back.',
    )
    # Workday settings
    df_geodynamics_workday_start = fields.Float(
        string='Workday Start Hour', default=6.0,
        config_parameter='geodynamics.workday_start'
    )
    df_geodynamics_workday_end = fields.Float(
        string='Workday End Hour', default=15.0,
        config_parameter='geodynamics.workday_end'
    )
    # API Logging
    df_geodynamics_enable_api_logging = fields.Boolean(
        string='Enable API Logging', default=False,
        config_parameter='geodynamics.enable_api_logging'
    )
    df_geodynamics_api_log_retention_days = fields.Integer(
        string='API Log Retention (days)', default=30,
        config_parameter='geodynamics.api_log_retention_days'
    )
    df_geodynamics_verbose_logging = fields.Boolean(
        string='Verbose Logging',
        default=False,
        config_parameter='geodynamics.verbose_logging',
    )
    # Event type filter for postcalc import
    df_geodynamics_import_event_types = fields.Many2many(
        'df.geodynamics.event.type', string='Event types to import',
        help='Select which event types to import during post-calculation. Leave empty to import all.',
    )
    # Checkin at Work
    df_geodynamics_enable_checkin = fields.Boolean(
        string='Enable Checkin at Work', default=False,
        config_parameter='geodynamics.enable_checkin'
    )
    df_geodynamics_checkin_from_date = fields.Char(
        string='Import checkins since',
        config_parameter='geodynamics.checkin_from_date',
        help='Date in YYYY-MM-DD format',
    )
    # Leave import
    df_geodynamics_leave_from_date = fields.Char(
        string='Import leaves since',
        config_parameter='geodynamics.leave_from_date',
        help='Date in YYYY-MM-DD format',
    )
    df_geodynamics_leave_to_date = fields.Char(
        string='Import leaves until',
        config_parameter='geodynamics.leave_to_date',
        help='Date in YYYY-MM-DD format. Leave empty for today.',
    )
    # Leave import options
    df_geodynamics_auto_approve_leave = fields.Boolean(
        string='Auto-approve leaves on import',
        default=False,
        config_parameter='geodynamics.auto_approve_leave',
    )
    # Employee matching
    df_geodynamics_match_by_email = fields.Boolean(
        string='Match Employees by Email',
        default=False,
        config_parameter='geodynamics.match_by_email',
        help='When importing or exporting employees, match existing employees by their email address '
             '(work email, private email, or linked user email) to avoid duplicates.',
    )
    # Fleet matching
    df_geodynamics_match_fleet_by_plate = fields.Boolean(
        string='Match Vehicles by License Plate',
        default=False,
        config_parameter='geodynamics.match_fleet_by_plate',
        help='When importing or exporting vehicles, match existing vehicles by their license plate to avoid duplicates.',
    )

    def set_values(self):
        super().set_values()
        codes = ','.join(self.df_geodynamics_import_event_types.mapped('df_code'))
        self.env['ir.config_parameter'].sudo().set_param('geodynamics.import_event_types', codes)

    @api.model
    def get_values(self):
        res = super().get_values()
        codes_str = self.env['ir.config_parameter'].sudo().get_param('geodynamics.import_event_types', '')
        if codes_str:
            codes = [c.strip() for c in codes_str.split(',') if c.strip()]
            event_types = self.env['df.geodynamics.event.type'].search([('df_code', 'in', codes)])
            res['df_geodynamics_import_event_types'] = [(6, 0, event_types.ids)]
        return res

    # --- Verbose logging helper ---

    def _gd_verbose_log(self, message):
        """Write a verbose processing log entry if verbose logging is enabled."""
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('geodynamics.verbose_logging', 'False').lower() not in ('true', '1', 'yes'):
            return
        _logger.info('[Geodynamics] %s', message)
        try:
            self.env['df.geodynamics.api.log'].sudo().create({
                'df_name': 'verbose',
                'df_method': 'LOG',
                'df_url': '',
                'df_request_payload': {'message': message},
                'df_response_status': 0,
                'df_duration_ms': 0,
            })
        except Exception:
            pass

    # --- Import / Export actions (called from Settings page) ---

    def _gd_match_by_email(self):
        """Read the match-by-email setting."""
        return self.env['ir.config_parameter'].sudo().get_param(
            'geodynamics.match_by_email', 'True').lower() in ('true', '1', 'yes')

    def gd_import_employees(self):
        """Import employees from Geodynamics into Odoo."""
        wizard = self.env['df.geodynamics.import.wizard'].create({
            'df_import_type': 'employees',
            'df_direction': 'import',
            'df_match_by_email': self._gd_match_by_email(),
        })
        return wizard._sync_employees()

    def gd_export_employees(self):
        """Export employees from Odoo to Geodynamics."""
        wizard = self.env['df.geodynamics.import.wizard'].create({
            'df_import_type': 'employees',
            'df_direction': 'export',
            'df_match_by_email': self._gd_match_by_email(),
        })
        return wizard._sync_employees()

    def gd_sync_employees(self):
        """Bidirectional sync of employees."""
        wizard = self.env['df.geodynamics.import.wizard'].create({
            'df_import_type': 'employees',
            'df_direction': 'sync',
            'df_match_by_email': self._gd_match_by_email(),
        })
        return wizard._sync_employees()

    def gd_sync_odometer(self):
        """Sync odometer readings (km) from Geodynamics for all linked vehicles."""
        vehicles = self.env['fleet.vehicle'].search([('df_geodynamics_id', '!=', False)])
        return vehicles.action_gd_sync_odometer()

    def gd_import_fleet(self):
        """Import fleet / vehicles from Geodynamics."""
        wizard = self.env['df.geodynamics.import.wizard'].create({
            'df_import_type': 'fleet',
            'df_direction': 'import',
        })
        return wizard._import_fleet()

    def gd_export_fleet(self):
        """Export fleet / vehicles to Geodynamics."""
        wizard = self.env['df.geodynamics.import.wizard'].create({
            'df_import_type': 'fleet',
            'df_direction': 'export',
        })
        return wizard._export_fleet()

    def gd_import_pois(self):
        """Import Points of Interest from Geodynamics."""
        wizard = self.env['df.geodynamics.import.wizard'].create({
            'df_import_type': 'pois',
            'df_direction': 'import',
        })
        return wizard._import_pois()

    def gd_import_checkins(self):
        """Import Checkin at Work records from Geodynamics."""
        from_date = self.env['ir.config_parameter'].sudo().get_param('geodynamics.checkin_from_date')
        if from_date:
            try:
                from_date = fields.Date.from_string(from_date)
            except (ValueError, TypeError):
                from_date = fields.Date.today()
        else:
            from_date = fields.Date.today()
        wizard = self.env['df.geodynamics.import.wizard'].create({
            'df_import_type': 'checkins',
            'df_direction': 'import',
            'df_date_from': from_date,
            'df_date_to': fields.Date.today(),
        })
        return wizard._import_checkins()

    def gd_link_leave_types(self):
        """Link Odoo leave types to Geodynamics absence types by matching names.

        Fetches the absence types from Geodynamics and, for every Odoo leave type
        whose name matches a Geodynamics absence type name (case-insensitive),
        stores that Geodynamics name in the 'Geodynamics' link field. Leave types
        without a match stay unlinked and remain outside the leave sync.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        company = ICP.get_param('geodynamics.company')
        login = ICP.get_param('geodynamics.username')
        password = ICP.get_param('geodynamics.password')
        if not all([company, login, password]):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Geodynamics',
                    'type': 'danger',
                    'message': 'Geodynamics API credentials are not configured.',
                    'sticky': False,
                },
            }

        handler = GeodynamicsHandler(login, password, company, self.env)
        gd_result = handler.getAbsenceTypes()
        if not gd_result.get('Success'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Geodynamics',
                    'type': 'danger',
                    'message': f'Failed to fetch absence types: {gd_result.get("Error", "Unknown error")}',
                    'sticky': True,
                },
            }

        gd_data = gd_result.get('Data', [])
        if isinstance(gd_data, dict):
            gd_data = gd_data.get('Data', [])
        gd_types = {}
        if isinstance(gd_data, list):
            for at in gd_data:
                if isinstance(at, dict) and at.get('Name'):
                    gd_types[at['Name'].strip().lower()] = at

        if not gd_types:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Geodynamics',
                    'type': 'warning',
                    'message': 'No absence types returned by Geodynamics.',
                    'sticky': True,
                },
            }

        leave_types = self.env['hr.leave.type'].sudo().search([])
        linked = 0
        unmatched = 0
        for lt in leave_types:
            gd_at = gd_types.get((lt.name or '').strip().lower())
            if gd_at:
                vals = {'df_geodynamics_name': gd_at.get('Name')}
                if gd_at.get('Id') and not lt.df_geodynamics_id:
                    vals['df_geodynamics_id'] = gd_at.get('Id')
                lt.write(vals)
                linked += 1
            else:
                unmatched += 1

        _logger.info('[Geodynamics] Leave type link: %d linked, %d without match', linked, unmatched)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Geodynamics Leave Type Link',
                'type': 'success',
                'message': f'{linked} leave types linked, {unmatched} without a matching Geodynamics absence type.',
                'sticky': True,
            },
        }

    def gd_export_leave_types(self):
        """Export all Odoo leave types to Geodynamics as absence types."""
        ICP = self.env['ir.config_parameter'].sudo()
        company = ICP.get_param('geodynamics.company')
        login = ICP.get_param('geodynamics.username')
        password = ICP.get_param('geodynamics.password')
        if not all([company, login, password]):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Geodynamics',
                    'type': 'danger',
                    'message': 'Geodynamics API credentials are not configured.',
                    'sticky': False,
                },
            }

        handler = GeodynamicsHandler(login, password, company, self.env)
        leave_types = self.env['hr.leave.type'].sudo().search([])

        gd_result = handler.getAbsenceTypes()
        existing_gd = {}
        if gd_result.get('Success'):
            gd_data = gd_result.get('Data', [])
            if isinstance(gd_data, dict):
                gd_data = gd_data.get('Data', [])
            if isinstance(gd_data, list):
                for at in gd_data:
                    if isinstance(at, dict) and at.get('Name'):
                        existing_gd[at['Name'].strip().lower()] = at

        created = 0
        matched = 0
        errors = 0
        for lt in leave_types:
            name_key = lt.name.strip().lower()
            try:
                if name_key in existing_gd:
                    gd_at = existing_gd[name_key]
                    link_vals = {}
                    if not lt.df_geodynamics_id:
                        link_vals['df_geodynamics_id'] = gd_at.get('Id')
                    if not lt.df_geodynamics_name:
                        link_vals['df_geodynamics_name'] = gd_at.get('Name')
                    if link_vals:
                        lt.sudo().write(link_vals)
                    matched += 1
                    _logger.info('[Geodynamics] Leave type "%s" already exists in Geodynamics (id=%s)',
                                 lt.name, gd_at.get('Id'))
                else:
                    ODOO_COLORS = {
                        0: '#FFFFFF', 1: '#F06050', 2: '#F4A460', 3: '#F7CD1F',
                        4: '#6CC1ED', 5: '#814968', 6: '#EB7E7F', 7: '#2C8397',
                        8: '#475577', 9: '#D6145F', 10: '#30C381', 11: '#9365B8',
                    }
                    color_hex = ODOO_COLORS.get(lt.color, '#808080')
                    result = handler.createAbsenceType({
                        'Name': lt.name,
                        'AbsenceCode': lt.name[:3].upper(),
                        'Color': color_hex,
                    })
                    if result.get('Success') and result.get('Data'):
                        gd_data = result['Data']
                        new_id = gd_data.get('Id') if isinstance(gd_data, dict) else None
                        link_vals = {}
                        if new_id:
                            link_vals['df_geodynamics_id'] = new_id
                        if not lt.df_geodynamics_name:
                            link_vals['df_geodynamics_name'] = lt.name
                        if link_vals:
                            lt.sudo().write(link_vals)
                        created += 1
                        _logger.info('[Geodynamics] Created absence type "%s" in Geodynamics (id=%s)',
                                     lt.name, new_id)
                    else:
                        errors += 1
                        _logger.warning('[Geodynamics] Failed to create absence type "%s": %s',
                                        lt.name, result)
            except Exception as e:
                errors += 1
                _logger.error('[Geodynamics] Error exporting leave type "%s": %s', lt.name, str(e))

        _logger.info('[Geodynamics] Leave type export: %d created, %d matched, %d errors', created, matched, errors)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Geodynamics Leave Type Export',
                'type': 'success' if not errors else 'warning',
                'message': f'{created} created, {matched} already exist, {errors} errors.',
                'sticky': True,
            },
        }

    def gd_import_leaves(self):
        """Import leaves/absences from Geodynamics into Odoo hr.leave using the UI date range."""
        ICP = self.env['ir.config_parameter'].sudo()

        from_date_str = ICP.get_param('geodynamics.leave_from_date')
        if from_date_str:
            try:
                from_date = fields.Date.from_string(from_date_str)
            except (ValueError, TypeError):
                from_date = fields.Date.today()
        else:
            from_date = fields.Date.today()

        to_date_str = ICP.get_param('geodynamics.leave_to_date')
        if to_date_str:
            try:
                to_date = fields.Date.from_string(to_date_str)
            except (ValueError, TypeError):
                to_date = fields.Date.today()
        else:
            to_date = fields.Date.today()

        stats = self._gd_import_leaves_range(from_date, to_date)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Geodynamics Leave Import',
                'type': 'success' if (stats['success'] and not stats['errors'])
                        else ('warning' if stats['success'] else 'danger'),
                'message': stats['message'],
                'sticky': True,
            },
        }

    @api.model
    def gd_cron_sync_leaves(self):
        """Cron: auto-sync leaves from Geodynamics to Odoo when enabled in Settings.

        Imports a rolling window of leave records (recent past + upcoming) so newly
        planned absences in Geodynamics automatically appear in Odoo without manual
        intervention.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('geodynamics.auto_sync_leaves', 'False').lower() not in ('true', '1', 'yes'):
            return
        try:
            months_back = int(ICP.get_param('geodynamics.leave_sync_months_back', '1'))
        except (ValueError, TypeError):
            months_back = 1
        try:
            months_forward = int(ICP.get_param('geodynamics.leave_sync_months_forward', '11'))
        except (ValueError, TypeError):
            months_forward = 11
        today = fields.Date.today()
        from_date = today - relativedelta(months=months_back)
        to_date = today + relativedelta(months=months_forward)
        _logger.info('[Geodynamics] Auto leave sync window: %s (-%d months) .. %s (+%d months)',
                     from_date, months_back, to_date, months_forward)
        stats = self._gd_import_leaves_range(from_date, to_date)
        if not stats['success']:
            _logger.warning('[Geodynamics] Auto leave sync skipped: %s', stats['message'])
        else:
            _logger.info('[Geodynamics] Auto leave sync: %s', stats['message'])

    @api.model
    def _gd_import_leaves_range(self, from_date, to_date):
        """Import leaves/absences from Geodynamics into Odoo hr.leave for a date range.

        Returns a dict: {'success': bool, 'message': str, 'created': int, 'skipped': int, 'errors': int}.
        Used by both the manual Settings button and the auto-sync cron.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        company = ICP.get_param('geodynamics.company')
        login = ICP.get_param('geodynamics.username')
        password = ICP.get_param('geodynamics.password')
        if not all([company, login, password]):
            return {
                'success': False,
                'message': 'Geodynamics API credentials are not configured.',
                'created': 0, 'skipped': 0, 'errors': 0,
            }

        handler = GeodynamicsHandler(login, password, company, self.env)

        employees = self.env['hr.employee'].sudo().search([('df_geodynamics_id', '!=', False)])
        user_ids = [emp.df_geodynamics_id for emp in employees]

        from_dt = datetime.combine(from_date, datetime.min.time())
        to_dt = datetime.combine(to_date, datetime.max.time())

        result = handler.getAbsences(from_dt, to_dt, userIds=user_ids)

        if not result.get('Success'):
            return {
                'success': False,
                'message': f'Failed to fetch absences: {result.get("Error", "Unknown error")}',
                'created': 0, 'skipped': 0, 'errors': 0,
            }

        api_data = result.get('Data', [])
        if isinstance(api_data, dict):
            api_data = api_data.get('Data', [])
        if not isinstance(api_data, list):
            api_data = []

        gd_id_to_emp = {emp.df_geodynamics_id: emp for emp in employees}

        leave_types = self.env['hr.leave.type'].sudo().search([])
        # Only leave types explicitly linked to Geodynamics (via the 'Geodynamics'
        # name field) take part in the sync. Unlinked types are left out.
        name_to_type = {
            lt.df_geodynamics_name.strip().lower(): lt
            for lt in leave_types
            if lt.df_geodynamics_name and lt.df_geodynamics_name.strip()
        }
        if not name_to_type:
            return {
                'success': False,
                'message': 'No leave types are linked to Geodynamics. Use "Link Leave Types" in Settings first.',
                'created': 0, 'skipped': 0, 'errors': 0,
            }

        created = 0
        skipped = 0
        errors = 0

        self._gd_verbose_log(
            f'Leave import started: {len(api_data)} user entries from API, '
            f'{len(gd_id_to_emp)} linked employees, '
            f'{len(name_to_type)} leave types in Odoo: {list(name_to_type.keys())}'
        )

        for user_entry in api_data:
            user_info = user_entry.get('User') or {}
            user_id = str(user_info.get('Id', ''))
            user_name = user_info.get('Name', 'Unknown')
            if not user_id or user_id not in gd_id_to_emp:
                self._gd_verbose_log(
                    f'SKIP user "{user_name}" (GD id={user_id}): not linked to an Odoo employee'
                )
                skipped += 1
                continue
            emp = gd_id_to_emp[user_id]
            absences_list = user_entry.get('Absences') or []
            self._gd_verbose_log(
                f'Processing user "{user_name}" → employee "{emp.name}" ({len(absences_list)} absences)'
            )

            for absence in absences_list:
                try:
                    absence_type = absence.get('AbsenceType') or {}
                    absence_name_raw = (absence_type.get('Name') or '').strip()
                    absence_name = absence_name_raw.lower()
                    if not absence_name or absence_name not in name_to_type:
                        self._gd_verbose_log(
                            f'  SKIP absence "{absence_name_raw}" for {emp.name}: '
                            f'no matching leave type in Odoo'
                        )
                        skipped += 1
                        continue
                    leave_type = name_to_type[absence_name]

                    absence_id = absence.get('Id', '')
                    start_raw = absence.get('Start')
                    stop_raw = absence.get('Stop')
                    date_raw = absence.get('Date')
                    duration_raw = absence.get('Duration')
                    self._gd_verbose_log(
                        f'  Processing absence "{absence_id}": type="{absence_name_raw}", '
                        f'Date={date_raw}, Start={start_raw}, Stop={stop_raw}, Duration={duration_raw}'
                    )
                    if not start_raw or not stop_raw:
                        self._gd_verbose_log(
                            f'  SKIP absence "{absence_name_raw}" for {emp.name}: '
                            f'missing Start ({start_raw}) or Stop ({stop_raw})'
                        )
                        skipped += 1
                        continue
                    start_dt = datetime.fromisoformat(str(start_raw).replace('Z', '+00:00'))
                    stop_dt = datetime.fromisoformat(str(stop_raw).replace('Z', '+00:00'))
                    self._gd_verbose_log(
                        f'    Parsed (tz-aware): start={start_dt}, stop={stop_dt}'
                    )
                    if start_dt.tzinfo is not None:
                        start_dt = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
                    if stop_dt.tzinfo is not None:
                        stop_dt = stop_dt.astimezone(timezone.utc).replace(tzinfo=None)
                    self._gd_verbose_log(
                        f'    Converted to UTC naive: start={start_dt}, stop={stop_dt}'
                    )

                    start_date = start_dt.date() if hasattr(start_dt, 'date') else start_dt
                    stop_date = stop_dt.date() if hasattr(stop_dt, 'date') else stop_dt
                    day_start = datetime.combine(start_date, datetime.min.time())
                    day_end = datetime.combine(stop_date, datetime.max.time())
                    auto_approve = ICP.get_param(
                        'geodynamics.auto_approve_leave', 'False'
                    ).lower() in ('true', '1', 'yes')
                    self.env.cr.execute(
                        "SELECT id, date_from, date_to, state FROM hr_leave "
                        "WHERE employee_id = %s AND holiday_status_id = %s "
                        "AND date_from >= %s AND date_from <= %s LIMIT 1",
                        (emp.id, leave_type.id, day_start, day_end)
                    )
                    dup_row = self.env.cr.fetchone()
                    if dup_row:
                        if auto_approve and dup_row[3] in ('draft', 'confirm'):
                            self.env.cr.execute(
                                "UPDATE hr_leave SET state = 'validate' WHERE id = %s",
                                (dup_row[0],)
                            )
                            self._gd_verbose_log(
                                f'  APPROVED existing leave id={dup_row[0]} for {emp.name} '
                                f'(was {dup_row[3]})'
                            )
                            created += 1
                        else:
                            self._gd_verbose_log(
                                f'  SKIP absence "{absence_name_raw}" {start_raw}→{stop_raw} '
                                f'for {emp.name}: already exists in Odoo (leave id={dup_row[0]}, '
                                f'date_from={dup_row[1]}, date_to={dup_row[2]}, state={dup_row[3]})'
                            )
                            skipped += 1
                        continue

                    orig_requires = leave_type.requires_allocation
                    if orig_requires != 'no':
                        self.env.cr.execute(
                            "UPDATE hr_leave_type SET requires_allocation = 'no' WHERE id = %s",
                            (leave_type.id,)
                        )
                        leave_type.invalidate_recordset(['requires_allocation'])
                    try:
                        leave = self.env['hr.leave'].sudo().with_context(
                            leave_skip_date_check=True,
                            tracking_disable=True,
                            leave_fast_create=True,
                        ).create({
                            'employee_id': emp.id,
                            'holiday_status_id': leave_type.id,
                            'request_date_from': start_date,
                            'request_date_to': stop_date,
                            'date_from': start_dt,
                            'date_to': stop_dt,
                            'name': f'Geodynamics: {leave_type.name}',
                        })
                    finally:
                        if orig_requires != 'no':
                            self.env.cr.execute(
                                "UPDATE hr_leave_type SET requires_allocation = %s WHERE id = %s",
                                (orig_requires, leave_type.id,)
                            )
                            leave_type.invalidate_recordset(['requires_allocation'])
                    num_days = max(1.0, (stop_date - start_date).days + 1)
                    num_hours = num_days * 8.0
                    if num_days == 1:
                        duration_display = '1 dag'
                    else:
                        duration_display = f'{int(num_days)} dagen'
                    gd_label = f'Geodynamics: {leave_type.name}'
                    self.env.cr.execute(
                        "UPDATE hr_leave "
                        "SET date_from = %s, date_to = %s, "
                        "    request_date_from = %s, request_date_to = %s, "
                        "    number_of_days = %s, number_of_hours = %s, "
                        "    duration_display = %s, "
                        "    private_name = %s "
                        "WHERE id = %s",
                        (start_dt, stop_dt, start_date, stop_date,
                         num_days, num_hours, duration_display,
                         gd_label, leave.id)
                    )
                    self._gd_verbose_log(
                        f'    Leave id={leave.id}: SQL forced dates '
                        f'date_from={start_dt}, date_to={stop_dt}, '
                        f'number_of_days={num_days}, duration_display={duration_display}'
                    )
                    if auto_approve:
                        self.env.cr.execute(
                            "UPDATE hr_leave SET state = 'validate' WHERE id = %s",
                            (leave.id,)
                        )
                    status = 'APPROVED' if auto_approve else 'CREATED (draft)'
                    self._gd_verbose_log(
                        f'  {status} leave "{leave_type.name}" {start_raw}→{stop_raw} for {emp.name}'
                    )
                    created += 1
                except Exception as e:
                    errors += 1
                    tb = traceback.format_exc()
                    self._gd_verbose_log(
                        f'  ERROR for {emp.name}, absence "{absence.get("Id", "")}": {str(e)}\n{tb}'
                    )
                    _logger.error('[Geodynamics] Leave import error for user %s (%s), absence %s: %s\n%s',
                                  user_name, user_id, absence.get('Id', ''), str(e), tb)

        _logger.info('[Geodynamics] Leave import complete: %d created, %d skipped, %d errors', created, skipped, errors)
        return {
            'success': True,
            'message': f'{created} leaves imported, {skipped} skipped (duplicate or unmapped), {errors} errors.',
            'created': created, 'skipped': skipped, 'errors': errors,
        }

    def gd_eliminate_double_leaves(self):
        """Delete duplicate leave records: keeps the oldest leave per (employee, leave type, date)."""
        self.env.cr.execute("""
            SELECT hl.id FROM hr_leave hl
            INNER JOIN (
                SELECT employee_id, holiday_status_id, date(date_from) AS d,
                       MIN(id) AS keep_id, COUNT(*) AS cnt
                FROM hr_leave
                WHERE holiday_status_id IS NOT NULL
                GROUP BY employee_id, holiday_status_id, date(date_from)
                HAVING COUNT(*) > 1
            ) dups ON hl.employee_id = dups.employee_id
                  AND hl.holiday_status_id = dups.holiday_status_id
                  AND date(hl.date_from) = dups.d
                  AND hl.id != dups.keep_id
        """)
        dup_ids = [row[0] for row in self.env.cr.fetchall()]
        deleted = 0
        if dup_ids:
            leaves = self.env['hr.leave'].sudo().browse(dup_ids)
            for leave in leaves:
                try:
                    if leave.state not in ('draft', 'confirm'):
                        leave.with_context(leave_skip_date_check=True).action_draft()
                    leave.with_context(leave_skip_date_check=True).unlink()
                    deleted += 1
                except Exception as e:
                    _logger.warning('[Geodynamics] Could not delete duplicate leave %d: %s', leave.id, e)
        self.env.cr.execute("""
            UPDATE hr_leave
            SET number_of_days = GREATEST(1, date(date_to) - date(date_from) + 1),
                number_of_hours = GREATEST(1, date(date_to) - date(date_from) + 1) * 8.0,
                duration_display = CASE
                    WHEN GREATEST(1, date(date_to) - date(date_from) + 1) = 1 THEN '1 dag'
                    ELSE GREATEST(1, date(date_to) - date(date_from) + 1)::int::text || ' dagen'
                END
            WHERE number_of_days IS NULL
               OR number_of_days <= 0
               OR duration_display IS NULL
               OR duration_display = ''
               OR duration_display LIKE '0 %'
               OR duration_display LIKE '0.%'
               OR private_name LIKE 'Geodynamics:%'
        """)
        repaired = self.env.cr.rowcount
        _logger.info('[Geodynamics] Eliminate doubles: %d duplicates found, %d deleted, %d labels repaired',
                     len(dup_ids), deleted, repaired)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Geodynamics',
                'type': 'success',
                'message': f'{deleted} duplicate leaves deleted, {repaired} labels repaired.',
                'sticky': False,
            },
        }

    def gd_get_handler(self):
        """Retrieve or create an instance of GeodynamicsHandler"""
        if 'gd_handler' not in self.env.context:
            if not self.df_geodynamics_login or not self.df_geodynamics_password or not self.df_geodynamics_company:
                raise ValueError("Geodynamics credentials are missing.")

            handler = GeodynamicsHandler(self.df_geodynamics_login, self.df_geodynamics_password, self.df_geodynamics_company, self.env)
            self = self.with_context(gd_handler=handler)  # Store in context
        return self.env.context['gd_handler']

    def gd_test_verbinding(self):
        """Test connection with Geodynamics"""
        if not self.df_geodynamics_login or not self.df_geodynamics_password or not self.df_geodynamics_company:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': "Error",
                    'type': 'danger',
                    'message': 'Login, password, and company are required to test the connection.',
                },
            }

        try:
            testRes = self.gd_get_handler().test()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': "Webservice Status",
                    'type': testRes[0],
                    'message': testRes[1]
                },
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': "Connection Error",
                    'type': 'danger',
                    'message': f"An error occurred: {str(e)}",
                },
            }

    def gd_fetch_planningen(self):
        """Load plannings from Geodynamics — runs in background via cron."""
        from datetime import datetime as dt, timedelta

        # Calculate estimated API calls
        ICP = self.env['ir.config_parameter'].sudo()
        from_date_str = ICP.get_param('geodynamics.planning_from_date')
        if from_date_str:
            try:
                start_date = dt.strptime(from_date_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                start_date = dt.now() - timedelta(days=90)
        else:
            sync_days = 90
            try:
                sync_days = int(ICP.get_param('geodynamics.sync_days_back', '90'))
            except (ValueError, TypeError):
                pass
            start_date = dt.now() - timedelta(days=sync_days)
        end_date = dt.now() + timedelta(days=30)

        employees = self.env['hr.employee'].sudo().search([('df_geodynamics_id', '!=', False)])
        total_days = max(1, (end_date - start_date).days)
        chunks_per_emp = max(1, total_days // 30 + 1)
        total_calls = chunks_per_emp * len(employees)

        # Rate limit: 1800 requests per 30 min = 60/min
        rate_limit = 1800
        estimated_seconds = total_calls * 1  # ~1 second per call (request + processing)
        estimated_minutes = max(1, estimated_seconds // 60)

        if total_calls > rate_limit:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Geodynamics Planning Import',
                    'type': 'warning',
                    'message': (
                        f'Too many API calls needed: {total_calls} calls for {len(employees)} employees '
                        f'over {total_days} days. API rate limit is {rate_limit} per 30 min. '
                        f'Please set a more recent "From date" to reduce the range.'
                    ),
                    'sticky': True,
                },
            }

        # Schedule as background cron job
        cron_model = self.env['ir.cron'].sudo()
        existing_cron = cron_model.search([('name', '=', 'Geodynamics: Load Plannings (background)')], limit=1)
        if existing_cron:
            existing_cron.write({
                'active': True,
                'nextcall': fields.Datetime.now(),
            })
        else:
            cron_model.create({
                'name': 'Geodynamics: Load Plannings (background)',
                'model_id': self.env['ir.model']._get('res.config.settings').id,
                'state': 'code',
                'code': 'env["res.config.settings"]._gd_run_planning_import()',
                'interval_number': 365,
                'interval_type': 'days',
                'active': True,
                'nextcall': fields.Datetime.now(),
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Geodynamics Planning Import',
                'type': 'info',
                'message': (
                    f'Planning import started in background: ~{total_calls} API calls '
                    f'for {len(employees)} employees over {total_days} days. '
                    f'Estimated time: ~{estimated_minutes} minute(s). '
                    f'Check the server logs for progress.'
                ),
                'sticky': True,
            },
        }

    @api.model
    def _gd_run_planning_import(self):
        """Background method called by cron to load plannings."""
        ICP = self.env['ir.config_parameter'].sudo()
        company = ICP.get_param('geodynamics.company')
        login = ICP.get_param('geodynamics.username')
        password = ICP.get_param('geodynamics.password')
        if not all([company, login, password]):
            _logger.error('[Geodynamics] Cannot run planning import: API credentials missing')
            return
        from .gdhandler import GeodynamicsHandler
        handler = GeodynamicsHandler(login, password, company, self.env)
        handler.laadAllPlanning()

    def gd_poitype_to_odoo(self):
        handler = self.gd_get_handler()
        handler.laadPoiTypes()

    def _wn_pers_gd(self):
        for record in self:
            output = []

            for usr in self.env['hr.employee'].search([]):
                output.append(usr.id)

            record.df_persones_gd_ids = output




