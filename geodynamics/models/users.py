from odoo import models, fields, api

class Project(models.Model):
    _inherit = 'res.users'

    df_geodynamics_id = fields.Char('Sleutel Geodynamics')