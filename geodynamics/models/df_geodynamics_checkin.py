# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api, _


class GeodynamicsCheckin(models.Model):
    _name = 'df.geodynamics.checkin'
    _description = 'Checkin at Work (CIAW)'
    _order = 'df_checkin_time desc'
    _rec_name = 'display_name'

    df_employee_id = fields.Many2one('hr.employee', string='Employee', index=True, ondelete='cascade')
    df_checkin_time = fields.Datetime(string='Check-in Time', required=True, index=True)
    df_checkout_time = fields.Datetime(string='Check-out Time')
    df_construction_site = fields.Char(string='Construction Site')
    df_site_address = fields.Char(string='Site Address')
    df_project_id = fields.Many2one('project.project', string='Project', index=True)
    df_task_id = fields.Many2one('project.task', string='Task', index=True)
    df_geodynamics_id = fields.Char(string='Geodynamics ID', index=True)
    df_status = fields.Selection([
        ('checked_in', 'Checked In'),
        ('checked_out', 'Checked Out'),
        ('error', 'Error'),
    ], string='Status', default='checked_in')
    df_duration_hours = fields.Float(string='Duration (hours)', compute='_compute_duration', store=True)
    df_date = fields.Date(string='Date', compute='_compute_date', store=True, index=True)
    df_raw_payload = fields.Json(string='Raw Data')
    display_name = fields.Char(compute='_compute_display_name')

    _sql_constraints = [
        ('geodynamics_checkin_gd_id_uniq', 'UNIQUE(df_geodynamics_id)',
         'Geodynamics check-in ID must be unique.'),
    ]

    @api.depends('df_checkin_time', 'df_checkout_time')
    def _compute_duration(self):
        for rec in self:
            if rec.df_checkin_time and rec.df_checkout_time:
                delta = rec.df_checkout_time - rec.df_checkin_time
                rec.df_duration_hours = round(delta.total_seconds() / 3600.0, 2)
            else:
                rec.df_duration_hours = 0.0

    @api.depends('df_checkin_time')
    def _compute_date(self):
        for rec in self:
            rec.df_date = rec.df_checkin_time.date() if rec.df_checkin_time else False

    def _compute_display_name(self):
        for rec in self:
            emp = rec.df_employee_id.name or ''
            site = rec.df_construction_site or ''
            rec.display_name = f'{emp} - {site}' if site else emp
