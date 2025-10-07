from odoo import models, fields, api

from . import gdhandler
from .gdhandler import GeodynamicsHandler

import logging
_logger = logging.getLogger(__name__)

class Contact(models.Model):
    _inherit = 'res.partner'

    df_geodynamics_poi_id = fields.Char('Poi ID Geodynamics')

    df_geodynamics_error_message = fields.Char('Foutboodschap Geodynamics')

    supplier_invoice_count = fields.Integer()
    hide_peppol_fields = fields.Boolean()
    is_coa_installed = fields.Boolean()

    def sync_poi_geodynamics(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        for record in self:
            if record.df_geodynamics_poi_id == False:
                sResult = gdHandler.addPoi(record)

                _logger.info(str(sResult))

                if 'Error' in sResult.keys():
                    record.df_geodynamics_error_message = sResult['Error']
                else:
                    record.df_geodynamics_poi_id = sResult['Succes']['Id']
                    record.df_geodynamics_error_message = ''
            else:
                sResult = gdHandler.addPoi(record)
                if 'Error' in sResult.keys():
                    record.df_geodynamics_error_message = sResult['Error']
                else:
                    record.df_geodynamics_poi_id = sResult['Succes']['Id']
                    record.df_geodynamics_error_message = ''