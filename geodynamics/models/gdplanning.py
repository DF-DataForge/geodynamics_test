from odoo import models, fields, api

from . import gdhandler
from .gdhandler import GeodynamicsHandler
from datetime import datetime, timedelta

class GeodynamicsPlanning(models.Model):
    _name = 'df.geodynamics.planning'
    _description = 'Geodynamics Planning'

    start_datetime = fields.Datetime(string="Van", required=True)
    end_datetime = fields.Datetime(string="Tot", required=True)
    id_geodynamics = fields.Char(string="Geodynamics ID", required=True, unique=True)
    user_id_geodynamics = fields.Char(string="User ID Geodynamics")
    task_id = fields.Many2one(comodel_name='project.task', string='Gekoppelde taak')
    project_id = fields.Many2one(comodel_name='project.project', string='Project')
    employee_id = fields.Many2one(comodel_name='hr.employee', string='Werknemer')
    user_id = fields.Many2one(comodel_name='res.users', string='Gebruiker')
    activitynumber = fields.Char(string='Activity number')
    decription = fields.Char(string='Description')

    display_name = fields.Char(compute='_compute_display_name')
    display_name_with_task = fields.Char(compute='_compute_display_name_with_task')

    def _compute_display_name(self):
        for record in self:
            dStart = record.start_datetime + timedelta(hours=2)
            dEnd = record.end_datetime + timedelta(hours = 2)

            sDisplayName = str(record.employee_id.name) + ' - ' + dStart.strftime('%d/%m %H:%M') + ' -> ' + dEnd.strftime('%d/%m %H:%M')

            if record.task_id:
                sDisplayName = sDisplayName + ' (' + record.task_id.df_gd_name + ')'

            record.display_name = sDisplayName

    def _compute_display_name_with_task(self):
        for record in self:
            if record.task_id :
                record.display_name_with_task = '[' + record.task_id.name + '] ' + str(record.employee_id.name) + ' - ' + record.start_datetime.strftime(
                    '%d/%m %H:%M') + '->' + record.end_datetime.strftime('%d/%m %H:%M')
            else:
                record.display_name_with_task = str(record.employee_id.name) + ' - ' + record.start_datetime.strftime('%d/%m %H:%M') + '->' + record.end_datetime.strftime('%d/%m %H:%M')


    def removePlanning(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        for record in self:
            gdHandler.removePlanning(record.id_geodynamics)
            record.unlink()
