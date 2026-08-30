from odoo import models, fields, _

class EmployeeDf(models.Model):
    _inherit = 'hr.employee'

    df_geodynamics_id = fields.Char('Sleutel Geodynamics')
    df_timesheet_group_ids = fields.Many2many(
        'employee.timesheet.group',
        'employee_timesheet_group_rel',
        'employee_id',
        'group_id',
        string='Timesheet Groups'
    )
    df_geodynamics_last_sync = fields.Datetime(string='Last Geodynamics Sync')
    df_geodynamics_raw = fields.Json(string='Geodynamics Raw Data')

    def action_gd_export_employees(self):
        """Export selected employees to Geodynamics (callable from list view button)."""
        match_by_email = self.env['ir.config_parameter'].sudo().get_param(
            'geodynamics.match_by_email', 'True').lower() in ('true', '1', 'yes')
        wizard = self.env['df.geodynamics.import.wizard'].create({
            'df_import_type': 'employees',
            'df_direction': 'export',
            'df_match_by_email': match_by_email,
        })
        return wizard._sync_employees(employee_ids=self)
