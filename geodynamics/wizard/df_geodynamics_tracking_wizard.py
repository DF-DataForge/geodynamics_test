from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..models.gdhandler import GeodynamicsHandler
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class GeodynamicsTrackingWizard(models.TransientModel):
    _name = 'df.geodynamics.tracking.wizard'
    _description = 'Fetch Tracking Data'

    df_date_from = fields.Date(required=True, default=lambda self: fields.Date.today())
    df_date_to = fields.Date(required=True, default=lambda self: fields.Date.today())
    df_employee_ids = fields.Many2many('hr.employee', string='Employees',
                                    domain=[('df_geodynamics_id', '!=', False)])

    def _get_handler(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')
        if not all([company, login, password]):
            raise UserError(_('Geodynamics API credentials are not configured.'))
        return GeodynamicsHandler(login, password, company, self.env)

    def action_fetch(self):
        self.ensure_one()
        handler = self._get_handler()

        employees = self.df_employee_ids or self.env['hr.employee'].sudo().search(
            [('df_geodynamics_id', '!=', False)])

        resource_ids = [emp.df_geodynamics_id for emp in employees if emp.df_geodynamics_id]
        if not resource_ids:
            raise UserError(_('No employees with Geodynamics IDs found.'))

        result = handler.getLocationsByResourcesAndDate(
            resource_ids, from_day=self.df_date_from, to_day=self.df_date_to)

        if 'Error' in result:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Tracking Error'),
                    'type': 'danger',
                    'message': result['Error'],
                },
            }

        Tracking = self.env['df.geodynamics.tracking'].sudo()
        data = result.get('Data', [])
        if not isinstance(data, list):
            data = [data]

        created = 0
        emp_map = {emp.df_geodynamics_id: emp for emp in employees}

        for entry in data:
            if not isinstance(entry, dict):
                continue
            resource_id = entry.get('ResourceId') or entry.get('Id', '')
            positions = entry.get('Positions', [entry]) if 'Positions' in entry else [entry]

            for pos in positions:
                if not isinstance(pos, dict):
                    continue
                ts = pos.get('DateTime') or pos.get('Timestamp') or pos.get('DateTimeUtc')
                if not ts:
                    continue
                timestamp = handler._parse_input_dt(ts) if isinstance(ts, str) else ts

                emp = emp_map.get(resource_id)
                vals = {
                    'df_employee_id': emp.id if emp else False,
                    'df_timestamp': timestamp,
                    'df_latitude': pos.get('Latitude', 0.0),
                    'df_longitude': pos.get('Longitude', 0.0),
                    'df_speed': pos.get('Speed', 0.0),
                    'df_address': pos.get('Address', ''),
                    'df_status': pos.get('Status', '').lower() if pos.get('Status') else False,
                    'df_distance_km': pos.get('Distance', 0.0),
                    'df_raw_payload': pos,
                }
                Tracking.create(vals)
                created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tracking Data'),
                'type': 'success',
                'message': _('%d tracking records created.') % created,
            },
        }
