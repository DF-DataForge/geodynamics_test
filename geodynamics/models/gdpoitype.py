from odoo import models, fields, api

from . import gdhandler
from .gdhandler import GeodynamicsHandler

class GeodynamicsPoiType(models.Model):
    _name = 'df.geodynamics.poitype'
    _description = 'Geodynamics POI type'

    id_geodynamics = fields.Char('Id Geodynamics')
    Name = fields.Char('Naam')
    Color = fields.Char('Color')
