from odoo import models, fields, api

from . import gdhandler
from .gdhandler import GeodynamicsHandler
from datetime import datetime, timedelta

class Project(models.Model):
    _inherit = 'project.project'

    df_gd_employee_ids = fields.Many2many('hr.employee', string='Werknemers Geodynamics', domain=[('df_geodynamics_id','!=',False)])

    def sendPlanningToDGd(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        for record in self:
            print(record.date_start)
            print(record.date)

            current_date = record.date_start
            while current_date <= record.date:
                print(current_date)

                for emp in self.df_gd_employee_ids:
                    gdHandler.createPlanning(emp.df_geodynamics_id, self.date_to_datetime(current_date, 3, 0) , self.date_to_datetime(current_date, 3, 15), record.name)

                current_date += timedelta(days=1)

    def laadPostcalc(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        for record in self:
            current_date = record.date_start

            registratieTaak = self.env['project.task'].search([('project_id','=',record.id),('name','=','Registratie Geodynamics')])

            if not registratieTaak:
                self.env['project.task'].create({'project_id':record.id,'name':'Registratie Geodynamics'})

                registratieTaak = self.env['project.task'].search([('project_id', '=', record.id), ('name', '=', 'Registratie Geodynamics')])

            print(registratieTaak)

            while current_date <= record.date:
                print(current_date)

                for emp in self.df_gd_employee_ids:
                    data = gdHandler.laadPostcalc(emp.df_geodynamics_id, self.date_to_datetime(current_date, 0, 0))

                    print('Data: ')
                    print(str(data))

                    for entry in data.get("Data", []):
                        for event in entry.get("PostCalculationEvents", []):
                            cost_center = event.get("CostCenterFullCode", "N/A")
                            duration = event.get("Duration", 0)
                            print(f"CostCenterFullCode: {cost_center}, Duration: {duration}")

                            if cost_center == record.name or True:
                                print('match')

                                currentTimesheet = self.env['account.analytic.line'].search([('account_id','=',record.account_id.id),('employee_id','=',emp.id),('date','=',current_date),('task_id','=',registratieTaak.id)])
                                print(currentTimesheet)

                                if not currentTimesheet:
                                    self.env['account.analytic.line'].create({'account_id':record.account_id.id,'date':current_date, 'task_id':registratieTaak.id, 'employee_id':emp.id, 'name':'Registratie Geodynamics', 'unit_amount':duration})
                                else:
                                    print('Updating timesheet...')
                                    currentTimesheet.write({'unit_amount':duration})

                current_date += timedelta(days=1)


    def date_to_datetime(self, d, hours, minutes):
        return datetime.combine(d, datetime.min.time().replace(hour=hours, minute=minutes))

