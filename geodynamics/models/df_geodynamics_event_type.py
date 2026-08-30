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
