from odoo import models, fields, api

from . import gdhandler
from .gdhandler import GeodynamicsHandler
from datetime import datetime, timedelta

class GeodynamicsPlanning(models.Model):
    _name = 'df.geodynamics.planning'
    _description = 'Geodynamics Planning'
    _rec_name = 'activitynumber'

    start_datetime = fields.Datetime(string="Van", required=True)
    end_datetime = fields.Datetime(string="Tot", required=True)
    id_geodynamics = fields.Char(string="Geodynamics ID", required=True, unique=True)
    user_id_geodynamics = fields.Char(string="User ID Geodynamics")
    task_id = fields.Many2one(comodel_name='project.task', string='Gekoppelde taak')
    project_id = fields.Many2one(comodel_name='project.project', string='Project')
    employee_id = fields.Many2one(comodel_name='hr.employee', string='Werknemer')
    user_id = fields.Many2one(comodel_name='res.users', string='Gebruiker')
    activitynumber = fields.Char(string='Activity number')
    description = fields.Char(string='Description')
    df_color = fields.Integer(string='Color Index', compute='_compute_color')

    display_name_with_task = fields.Char(compute='_compute_display_name_with_task')

    @api.depends('task_id', 'employee_id', 'start_datetime', 'end_datetime')
    def _compute_display_name(self):
        """Show task, employee and planning period in tags/labels (e.g. overlap pills)."""
        for record in self:
            emp_name = record.employee_id.name or ''
            if record.start_datetime and record.end_datetime:
                period = '%s → %s' % (
                    record.start_datetime.strftime('%d/%m %H:%M'),
                    record.end_datetime.strftime('%d/%m %H:%M'),
                )
            else:
                period = ''
            if record.task_id:
                label = ('[%s] %s' % (record.task_id.name, emp_name)).strip()
            else:
                label = emp_name
            if period:
                label = ('%s - %s' % (label, period)) if label else period
            record.display_name = label or (record.activitynumber or '')

    def _compute_color(self):
        for record in self:
            record.df_color = (record.employee_id.id or 0) % 12

    def _compute_display_name_with_task(self):
        for record in self:
            if record.task_id :
                record.display_name_with_task = '[' + record.task_id.name + '] ' + str(record.employee_id.name) + ' - ' + record.start_datetime.strftime(
                    '%d/%m %H:%M') + '->' + record.end_datetime.strftime('%d/%m %H:%M')
            else:
                record.display_name_with_task = str(record.employee_id.name) + ' - ' + record.start_datetime.strftime('%d/%m %H:%M') + '->' + record.end_datetime.strftime('%d/%m %H:%M')


    def unlink(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        for record in self:
            if record.id_geodynamics:
                gdHandler.removePlanning(record.id_geodynamics)

        return super(GeodynamicsPlanning, self).unlink()

    def removePlanning(self):
        self.unlink()
