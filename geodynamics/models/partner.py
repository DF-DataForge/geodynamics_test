from odoo import models, fields, api

from . import gdhandler
from .gdhandler import GeodynamicsHandler

import logging
_logger = logging.getLogger(__name__)

class Contact(models.Model):
    _inherit = 'res.partner'

    df_geodynamics_poi_id = fields.Char('Poi ID Geodynamics')
    df_geodynamics_error_message = fields.Char('Foutboodschap Geodynamics')
    df_geodynamics_poi_name = fields.Char(string='POI Name')
    df_geodynamics_poi_type = fields.Char(string='POI Type')
    df_geodynamics_poi_lat = fields.Float(string='POI Latitude', digits=(10, 7))
    df_geodynamics_poi_lng = fields.Float(string='POI Longitude', digits=(10, 7))
    df_geodynamics_poi_raw = fields.Json(string='POI Raw Data')
    df_geodynamics_poi_last_sync = fields.Datetime(string='POI Last Synced')

    def sync_poi_geodynamics(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')

        if not all([company, login, password]):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Geodynamics',
                    'type': 'danger',
                    'message': 'Geodynamics API credentials are not configured. Go to Settings > Geodynamics.',
                    'sticky': False,
                },
            }

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        for record in self:
            try:
                if record.df_geodynamics_poi_id:
                    sResult = gdHandler.updatePoi(record)
                else:
                    sResult = gdHandler.addPoi(record)

                _logger.info('[Geodynamics] POI sync result for %s: %s', record.name, sResult)

                if 'Error' in sResult:
                    record.df_geodynamics_error_message = sResult['Error']
                    _logger.warning('[Geodynamics] POI sync error for %s: %s', record.name, sResult['Error'])
                elif 'Success' in sResult and isinstance(sResult['Success'], dict):
                    poi_data = sResult['Success']
                    record.df_geodynamics_poi_id = poi_data.get('Id', record.df_geodynamics_poi_id)
                    record.df_geodynamics_poi_name = poi_data.get('Name', record.df_geodynamics_poi_name)
                    record.df_geodynamics_poi_raw = poi_data
                    record.df_geodynamics_error_message = ''
                    record.df_geodynamics_poi_last_sync = fields.Datetime.now()
                    # Update coordinates from response
                    lat = poi_data.get('MarkerLat') or poi_data.get('Latitude') or poi_data.get('Lat')
                    lng = poi_data.get('MarkerLon') or poi_data.get('Longitude') or poi_data.get('Lng') or poi_data.get('Lon')
                    if lat:
                        record.partner_latitude = float(lat)
                    if lng:
                        record.partner_longitude = float(lng)
                    # Update POI type
                    poi_type = poi_data.get('PoiType')
                    if isinstance(poi_type, dict):
                        record.df_geodynamics_poi_type = poi_type.get('Name', '')
                    elif poi_type:
                        record.df_geodynamics_poi_type = str(poi_type)
                else:
                    record.df_geodynamics_error_message = 'Unexpected response from Geodynamics'
                    _logger.warning('[Geodynamics] POI sync unexpected response for %s: %s', record.name, sResult)
            except Exception as e:
                record.df_geodynamics_error_message = str(e)
                _logger.error('[Geodynamics] POI sync exception for %s: %s', record.name, e)

    def action_open_google_maps(self):
        self.ensure_one()
        url = 'https://www.google.com/maps?q=%s,%s' % (self.partner_latitude, self.partner_longitude)
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }