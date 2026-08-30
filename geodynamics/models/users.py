# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api

class Project(models.Model):
    _inherit = 'res.users'

    df_geodynamics_id = fields.Char('Sleutel Geodynamics')
    df_task_create_action = fields.Selection([
        ('add_poi', 'Add POI on task creation '),
        ('auto_plan', 'Planning on task creation')
    ], string='Task Workflow Action', default='auto_plan', help='Controls what happens in Geodynamics when a task is created and this user is selected on the task.')
