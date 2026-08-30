# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields


class GeodynamicsEventType(models.Model):
    _name = 'df.geodynamics.event.type'
    _description = 'Geodynamics Event Type'
    _order = 'df_code'

    name = fields.Char(string='Name', required=True)
    df_code = fields.Char(string='Code', required=True, index=True)

    _sql_constraints = [
        ('code_uniq', 'UNIQUE(df_code)', 'Event type code must be unique.'),
    ]
