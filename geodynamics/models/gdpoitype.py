# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api

from . import gdhandler
from .gdhandler import GeodynamicsHandler

class GeodynamicsPoiType(models.Model):
    _name = 'df.geodynamics.poitype'
    _description = 'Geodynamics POI type'

    id_geodynamics = fields.Char('Id Geodynamics')
    Name = fields.Char('Naam')
    Color = fields.Char('Color')
