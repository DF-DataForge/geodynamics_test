from odoo import models, fields

class EmployeeDf(models.Model):
    _inherit = 'hr.employee'

    df_geodynamics_id = fields.Char('Sleutel Geodynamics')