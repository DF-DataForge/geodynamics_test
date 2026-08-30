# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..models.gdhandler import GeodynamicsHandler
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class GeodynamicsCheckinWizard(models.TransientModel):
    _name = 'df.geodynamics.checkin.wizard'
    _description = 'Fetch Checkin at Work Data'

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

        from_dt = datetime.combine(self.df_date_from, datetime.min.time())
        to_dt = datetime.combine(self.df_date_to, datetime.max.time().replace(microsecond=0))

        Checkin = self.env['df.geodynamics.checkin'].sudo()
        created = 0

        for emp in employees:
            if not emp.df_geodynamics_id:
                continue
            result = handler.getCheckins(emp.df_geodynamics_id, from_dt, to_dt)
            if 'Error' in result:
                _logger.warning('[Geodynamics] Checkin fetch error for %s: %s', emp.name, result['Error'])
                continue

            checkins = result.get('Data', [])
            for ci in checkins:
                start_raw = ci.get('start', {})
                gd_id = start_raw.get('Id', '')
                if gd_id and Checkin.search([('df_geodynamics_id', '=', gd_id)], limit=1):
                    continue

                pois = ci.get('pois')
                site_name = ''
                site_address = ''
                if isinstance(pois, list) and pois:
                    first_poi = pois[0] if isinstance(pois[0], dict) else {}
                    site_name = first_poi.get('Name', '')
                    site_address = first_poi.get('Street', '')

                start_time = handler._parse_input_dt(ci.get('start_time')) if ci.get('start_time') else False
                stop_time = handler._parse_input_dt(ci.get('stop_time')) if ci.get('stop_time') else False

                vals = {
                    'df_employee_id': emp.id,
                    'df_checkin_time': start_time,
                    'df_checkout_time': stop_time,
                    'df_construction_site': site_name,
                    'df_site_address': site_address,
                    'df_geodynamics_id': gd_id or False,
                    'df_status': 'checked_out' if stop_time else 'checked_in',
                    'df_raw_payload': ci,
                }
                Checkin.create(vals)
                created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Checkin at Work'),
                'type': 'success',
                'message': _('%d check-in records created.') % created,
            },
        }
