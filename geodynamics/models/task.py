from odoo import models, fields, api

from . import gdhandler
from .gdhandler import GeodynamicsHandler
from datetime import datetime, timedelta
import logging

class Project(models.Model):
    _inherit = 'project.task'

    df_assignees_without_geodynamics_ids = fields.Many2many('res.users', string='Werknemers zonder geodynamics id', compute='_wn_zonder_gd')
    df_assignees_with_geodynamics_ids = fields.Many2many('res.users', string='Werknemers met geodynamics id',
                                                            compute='_wn_met_gd')

    df_gd_name = fields.Char(string='Geodynamics name', compute='_get_gd_name')

    employee_ids = fields.Many2many('hr.employee', string='Painters')

    df_workmode = fields.Selection(selection=[('employeemode','Employee'),('usermode','User')], compute='_get_workmode')

    df_employees_without_geodynamics_ids = fields.Many2many('hr.employee', string='Werknemers zonder geodynamics id', compute='_emp_zonder_gd')
    df_employees_with_geodynamics_ids = fields.Many2many('hr.employee', string='Werknemers zonder geodynamics id',
                                                            compute='_emp_met_gd')

    df_employees_without_geodynamics_ids_invisible = fields.Boolean(compute='_emp_zonder_gd')

    df_gd_planning_ids = fields.One2many(comodel_name='df.geodynamics.planning', inverse_name='task_id', string='Planningen Geodynamics', readonly=True)

    df_gd_planning_ids2 = fields.One2many(comodel_name='df.geodynamics.planning', string='Planningen Geodynamics', readOnly=True, compute='_get_planningen_ids2')

    df_gd_planning_overlapped_ids = fields.One2many(comodel_name='df.geodynamics.planning', string='Overlappende planningen Geodynamics',
                                          readOnly=True, compute='_get_overlapped_plannind_ids')

    df_gd_planning_overlapped_ids_invisible = fields.Boolean(compute='_get_overlapped_plannind_ids')

    def unlink(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        for record in self:
            gdHandler.removePlanning_task(record)


        return super(Project, self).unlink()

    def _get_planningen_ids2(self):
        for record in self:
            output = []
            plans = self.env['df.geodynamics.planning'].search([('task_id','=',record.id)])
            for p in plans:
                output.append(p.id)
            print('Assigning output: ' )
            if output == []:
                record.df_gd_planning_ids2 = False
            else:
                record.df_gd_planning_ids2 = output

    def _get_overlapped_plannind_ids(self):
        for record in self:
            plannedIds = set()
            for wn in record.df_employees_with_geodynamics_ids:
                startOverlaps = self.env['df.geodynamics.planning'].search(
                    [('employee_id', '=', wn.id), ('start_datetime', '>', record.planned_date_start),
                     ('start_datetime', '<', record.date_deadline), ('task_id', '!=', record.id)])
                for s in startOverlaps:
                    plannedIds.add(s.id)

                endOverlaps = self.env['df.geodynamics.planning'].search(
                    [('employee_id', '=', wn.id), ('end_datetime', '>', record.planned_date_start),
                     ('end_datetime', '<', record.date_deadline), ('task_id', '!=', record.id)])
                for s in startOverlaps:
                    plannedIds.add(s.id)

            if plannedIds:
                record.df_gd_planning_overlapped_ids = list(plannedIds)
                record.df_gd_planning_overlapped_ids_invisible = False
            else:
                record.df_gd_planning_overlapped_ids = False
                record.df_gd_planning_overlapped_ids_invisible = True


    def _get_workmode(self):
        for record in self:
            record.df_workmode = 'employeemode'

    def _get_gd_name(self):
        for record in self:
            #record.df_gd_name = record.project_id.name + ' / ' + record.name
            record.df_gd_name = record.name

    def _wn_zonder_gd(self):
        for record in self:
            output = []
            for us in record.user_ids:
                if us.df_geodynamics_id == False:
                    output.append(us.id)
            record.df_assignees_without_geodynamics_ids = output

    def _emp_met_gd(self):
        for record in self:
            output = []
            for us in record.employee_ids:
                if us.df_geodynamics_id != False:
                    output.append(us.id)
            record.df_employees_with_geodynamics_ids = output

    def _emp_zonder_gd(self):
        for record in self:
            output = []
            for us in record.employee_ids:
                if us.df_geodynamics_id == False:
                    output.append(us.id)
            record.df_employees_without_geodynamics_ids = output

            if output == []:
                record.df_employees_without_geodynamics_ids_invisible = True
            else:
                record.df_employees_without_geodynamics_ids_invisible = False

    def _wn_met_gd(self):
        for record in self:
            output = []
            for us in record.user_ids:
                if us.df_geodynamics_id != False:
                    output.append(us.id)
            record.df_assignees_with_geodynamics_ids = output

    def sendPlanningToDGd(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        #gdHandler.createPlanning(emp.df_geodynamics_id, self.date_to_datetime(current_date, 3, 0),
        #                         self.date_to_datetime(current_date, 3, 15), record.name)

        for record in self:
            if len(record.df_assignees_with_geodynamics_ids) == 0:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': "Geen planningen aangemaakt",
                        'type': 'danger',
                        'message': "Er zijn geen gebruikers met geodynamics id, dus kan geen planningen aanmaken",
                    },
                }
            else:
                gdHandler.createPlanningByTask(record)

    def testPeriods(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        gdHandler.testPeriods(self)

    def sendPlanningToDGdWn(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')
        overlapwarning = self.env['ir.config_parameter'].sudo().get_param('geodynamics.wapp')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        #gdHandler.createPlanning(emp.df_geodynamics_id, self.date_to_datetime(current_date, 3, 0),
        #                         self.date_to_datetime(current_date, 3, 15), record.name)

        totalPlanned = 0
        totalDeleted = 0
        totalModified = 0
        for record in self:
            sRes = self.checkPlanItem(record)

            if sRes != []:
                return {
                                'type': 'ir.actions.client',
                                'tag': 'display_notification',
                                'params': {
                                    'title': "Geen planningen aangemaakt",
                                    'type': 'danger',
                                    'message': "Ken werknemers toe, en start- en stoptijden",
                                }
                            }

            print(overlapwarning)
            if len(record.df_gd_planning_overlapped_ids) > 0 and (overlapwarning == True or overlapwarning == 'True'):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': "Geen planningen aangemaakt",
                        'type': 'danger',
                        'message': "Let op, taak " + str(record.name) + " heeft overlappende planningen met andere taken. Gelieve eerst op deze taak de planningen in de Geodynamics module te wissen.",
                    }
                }


            #amountDeleted = gdHandler.deletePlanning2(record)

            print('Start create planning')

            if sRes == []:
                amountItemsPlanned = gdHandler.createPlanningByTaskWn(record)

                totalPlanned = totalPlanned + amountItemsPlanned

                print('Total planned: ' + str(totalPlanned))

        #if totalPlanned == 0:
        #        return {
        #            'type': 'ir.actions.client',
        #            'tag': 'display_notification',
        #            'params': {
        #                'title': "Geen planningen aangemaakt",
        #                'type': 'danger',
        #                'message': "Ken schilders toe, en start- en stoptijden",
        #            }
        #        }
        #else:
        #        self.reload()
        #        return {
        #            'type': 'ir.actions.client',
        #            'tag': 'display_notification',
        #            'params': {
        #                'title': "Planningen aangemaakt",
        #                'type': 'success',
        #                'message': "Er zijn " + str(totalPlanned) + " items aangemaakt",
        #            },
        #        }

    def autoPlan(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)
        planDirect = self.env['ir.config_parameter'].sudo().get_param('geodynamics.plandirectly')

        for record in self:
            print('In autoplan, record: ' + str(record.read()))
            if record.planned_date_start == False or record.date_deadline == False:
                print('need return')
                return

            for pId in record.df_gd_planning_overlapped_ids:
                gdHandler.deletePlanning3(pId.id)



            print('Calling task')
            amountItemsPlanned = gdHandler.createPlanningByTaskWn(record)

    def checkPlanItem(self, sRecord):
        sErrors = []
        if sRecord.planned_date_start == False or sRecord.date_deadline == False:
            sErrors.append('- Start- en einddatum zijn niet gekend')
        if len(sRecord.df_employees_with_geodynamics_ids) == 0:
            sErrors.append('- Geen schilders gekoppeld')
        return sErrors

    def testOverlap(self):
        for record in self:
            print('go')
            self.checkOverlap(record)

    def checkOverlap(self, sRecord):
        sErrors = []

        for wn in sRecord.df_employees_with_geodynamics_ids:
            print('Examine... ' + wn.name)
            print('Start: ' + str(sRecord.planned_date_start))
            print('End: ' + str(sRecord.date_deadline))
            startOverlaps = self.env['df.geodynamics.planning'].search([('employee_id','=',wn.id),('start_datetime','>',sRecord.planned_date_start),('start_datetime', '<', sRecord.date_deadline),('task_id','!=',sRecord.id)])

            for s in startOverlaps:
                print(s.display_name_with_task)

    def laadPostcalcOld(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        for record in self:
            for usr in record.df_assignees_with_geodynamics_ids:
                sDate = record.date_deadline.date()
                print(sDate)
                data = gdHandler.laadPostcalc(usr.df_geodynamics_id, self.date_to_datetime(sDate, 0, 0))

                print('Data: ')
                print(str(data))

                for entry in data.get("Data", []):
                    for event in entry.get("PostCalculationEvents", []):
                        cost_center = event.get("CostCenterFullCode", "N/A")
                        duration = event.get("Duration", 0)
                        print(f"CostCenterFullCode: {cost_center}, Duration: {duration}")

                        if cost_center == record.df_gd_name:
                            print('match')

                            emp = self.env['hr.employee'].search([('df_geodynamics_id','=',usr.df_geodynamics_id)])

                            currentTimesheet = self.env['account.analytic.line'].search(
                                [('account_id', '=', record.project_id.account_id.id), ('employee_id', '=', emp.id),
                                 ('date', '=', sDate), ('task_id', '=', record.id)])
                            print(currentTimesheet)

                            if not currentTimesheet:
                                self.env['account.analytic.line'].create(
                                    {'account_id': record.project_id.account_id.id, 'date': sDate,
                                     'task_id': record.id, 'employee_id': emp.id,
                                     'name': 'Registratie Geodynamics', 'unit_amount': duration})
                            else:
                                print('Updating timesheet...')
                                currentTimesheet.write({'unit_amount': duration})

    def date_to_datetime(self, d, hours, minutes):
        return datetime.combine(d, datetime.min.time().replace(hour=hours, minute=minutes))

    def calculate_time_difference(self, start, stop):
        # Convert the strings to datetime objects
        start_time = datetime.fromisoformat(start)
        stop_time = datetime.fromisoformat(stop)

        # Calculate the difference in hours
        time_difference = (stop_time - start_time).total_seconds() / 3600  # Convert seconds to hours

        # Return the result as a set
        return {'start':start_time, 'stop':stop_time, 'diff':time_difference}

    def reload(self):
        """
        Notify the frontend to reload data.
        """
        #_logger.info("Sending reload trigger to frontend")
        self.env["bus.bus"].sudo()._sendone(
            "broadcast", "page_refresh", {"model_name": self._name}
        )
        #_logger.info("Reload trigger sent successfully")

    @api.model
    def create(self, vals):
        record = super(Project, self).create(vals)
        # Auto-plan only if both dates are present

        record.autoPlan()

        return record

    def write(self, vals):
        res = super(Project, self).write(vals)
        # Check if relevant fields are updated
        if 'planned_date_start' in vals or 'date_deadline' in vals or 'employee_ids' in vals:
            for rec in self:
                # Make sure both dates exist before calling autoPlan
                if rec.planned_date_start and rec.date_deadline:
                    rec.autoPlan()
        return res

    def laadPostcalc(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')
        postcalcsource = self.env['ir.config_parameter'].sudo().get_param('geodynamics.postcalcsource')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        print('laadpostcalc')

        for record in self:
            for it in record.df_gd_planning_ids2:

                sDate = it.start_datetime.date()

                data = gdHandler.laadPostcalc(it.employee_id.df_geodynamics_id, self.date_to_datetime(sDate, 0, 0))

                print('Data got: ')
                print(data)
                print('Gd name: ' + record.df_gd_name.strip())


                for al in self.env['account.analytic.line'].search([('account_id','=',record.project_id.analytic_account_id.id),('date','=',sDate),('task_id','=',record.id),('employee_id','=',it.employee_id.id)]):
                    al.unlink()

                for entry in data.get("Data", []):
                    print(postcalcsource)
                    if postcalcsource == 'timesheet':
                        for event in entry.get("TimeSheetEvents", []):
                            print(event)

                            #if event['Type'] == 5 and event['JobNumber'] == record.df_gd_name:
                            if event['Type'] == 5 and event['JobNumber'].strip().lower() == record.df_gd_name.strip().lower():

                                #'df_gd_type':int(event['Type']), 'df_gd_eventtype':int(event['EventType']),
                                duration = self.calculate_time_difference(event['StartDateTimeLocal'], event['StopDateTimeLocal'])
                                print(duration)
                                self.env['account.analytic.line'].create(
                                    {'account_id': record.project_id.analytic_account_id.id, 'date': sDate,
                                     'task_id': record.id, 'employee_id': it.employee_id.id,
                                     'name': 'Registratie Geodynamics',
                                     'df_gd_type': str(event['Type']), 'df_gd_eventtype': str(event['EventType']),
                                     'df_startTime': duration['start'], 'df_endTime':duration['stop'], 'unit_amount': duration['diff']})
                    elif postcalcsource == 'postcalculation':
                        for event in entry.get("PostCalculationEvents", []):
                            print(event)

                            if event['CostCenter'].strip().lower() == record.df_gd_name.strip().lower():

                                duration = self.calculate_time_difference(event['TimeFromLocal'], event['TimeToLocal'])

                                print(duration)
                                self.env['account.analytic.line'].create(
                                    {'account_id': record.project_id.analytic_account_id.id, 'date': sDate,
                                     'task_id': record.id, 'employee_id': it.employee_id.id,
                                     'name': 'Registratie Geodynamics',
                                     'df_startTime': duration['start'], 'df_endTime':duration['stop'], 'unit_amount': duration['diff']})




