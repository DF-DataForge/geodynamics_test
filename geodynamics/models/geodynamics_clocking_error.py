# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class GeodynamicsClockingPossibleError(models.Model):
    _name = 'geodynamics.clocking.possible.error'
    _description = 'Geodynamics Clocking Possible Error'
    _order = 'error_date desc, create_date desc'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    message = fields.Char(string='Message', required=True, default='Personen hebben afwijkende werktijd registratie')
    error_date = fields.Date(string='Error Date', required=True, index=True)
    project_code = fields.Char(string='Project Code', required=True, index=True)
    employee_details = fields.Text(string='Employee Details', help='Names and work time per employee')
    status = fields.Selection([
        ('to_check', 'Te controleren'),
        ('approved', 'Goedgekeurd'),
        ('fixed', 'Rechtgezet'),
        ('ignore', 'Negeren')
    ], string='Status', default='to_check', required=True, index=True)
    clocking_ids = fields.Many2many('geodynamics.clocking', string='Related Clockings')

    @api.depends('project_code', 'error_date')
    def _compute_name(self):
        for rec in self:
            if rec.project_code and rec.error_date:
                rec.name = f"{rec.project_code} - {rec.error_date}"
            else:
                rec.name = "Error"

    _sql_constraints = [
        ('unique_error_per_day_project',
         'UNIQUE(error_date, project_code)',
         'Only one error record per project per day is allowed.')
    ]

    def action_view_day_clockings(self):
        """Open list of all clockings for employees on the error date, grouped by employee"""
        self.ensure_one()

        if not self.error_date:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'type': 'warning',
                    'message': 'No error date defined.',
                },
            }

        # Get all employees from related clockings
        employee_ids = self.clocking_ids.mapped('employee_id').ids

        # Build domain to find all clockings for these employees on this date
        domain = [
            ('employee_id', 'in', employee_ids),
            ('date_local', '>=', f"{self.error_date} 00:00:00"),
            ('date_local', '<=', f"{self.error_date} 23:59:59"),
        ]

        return {
            'type': 'ir.actions.act_window',
            'name': f'Clockings on {self.error_date}',
            'res_model': 'geodynamics.clocking',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'search_default_group_by_employee': 1,  # Auto group by employee
                'default_date_local': self.error_date,
            },
            'target': 'current',
        }

