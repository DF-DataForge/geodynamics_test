from odoo import models, fields, api

from . import gdhandler
from .gdhandler import GeodynamicsHandler
from datetime import datetime, timedelta
import json
import logging
import re  # added

_logger = logging.getLogger(__name__)

class Project(models.Model):
    _inherit = 'project.task'

    df_gd_planning_task_enabled = fields.Boolean(compute='_compute_gd_planning_task_enabled')

    @api.depends_context('uid')
    def _compute_gd_planning_task_enabled(self):
        enabled = self.env['ir.config_parameter'].sudo().get_param('geodynamics.planning_task', 'True').lower() in ('true', '1', 'yes')
        for rec in self:
            rec.df_gd_planning_task_enabled = enabled

    df_assignees_without_geodynamics_ids = fields.Many2many('res.users', string='Werknemers zonder geodynamics id', compute='_wn_zonder_gd')
    df_assignees_with_geodynamics_ids = fields.Many2many('res.users', string='Werknemers met geodynamics id',
                                                            compute='_wn_met_gd')

    df_gd_name = fields.Char(string='Geodynamics name', compute='_get_gd_name')

    df_employee_ids = fields.Many2many('hr.employee', 'project_task_df_employee_ids_rel', 'task_id', 'employee_id', string='Painters', domain=[('df_geodynamics_id', '!=', False)])
    # Backward-compat: industry_fsm v17 defined employee_ids; removed in v19.
    # Stale views still reference it, so keep as a related delegate.
    employee_ids = fields.Many2many(related='df_employee_ids', string='Employees')

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

    # POI tracking field
    df_geodynamics_poi_id = fields.Char(string='Geodynamics POI ID', readonly=True, help='ID of the POI created in Geodynamics for this task')

    def unlink(self):
        company, login, password = self._get_geodynamic_configs()

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
            _logger.debug('Assigning output')
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
            # Append the task id so the Geodynamics ActivityNumber / CostCenter is
            # unique per task. Without it, two tasks sharing a name (e.g. the same
            # job for different customers) are indistinguishable and post-calculation
            # could be fetched onto the wrong task.
            if record.name:
                record.df_gd_name = '%s-%s' % (record.name, record.id)
            else:
                record.df_gd_name = str(record.id)

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
            for us in record.df_employee_ids:
                if us.df_geodynamics_id != False:
                    output.append(us.id)
            record.df_employees_with_geodynamics_ids = output

    def _emp_zonder_gd(self):
        for record in self:
            output = []
            for us in record.df_employee_ids:
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
        company, login, password = self._get_geodynamic_configs()

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
        company, login, password = self._get_geodynamic_configs()

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        gdHandler.testPeriods(self)

    def sendPlanningToDGdWn(self):
        company, login, password = self._get_geodynamic_configs()
        overlapwarning = self.env['ir.config_parameter'].sudo().get_param('geodynamics.wapp')
        wapp_on = overlapwarning in (True, 'True')
        ignore_overlap = self.env.context.get('gd_ignore_overlap')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        tasks_with_overlap = self.env['project.task']
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

            # When the new planning overlaps existing plannings, ask the user what to
            # do (keep existing / replace / don't plan) via a wizard instead of blocking.
            if (not ignore_overlap) and wapp_on and len(record.df_gd_planning_overlapped_ids) > 0:
                tasks_with_overlap |= record
                continue

            _logger.debug('Start create planning')
            gdHandler.createPlanningByTaskWn(record)

        if tasks_with_overlap:
            return {
                'type': 'ir.actions.act_window',
                'name': "Overlappende planningen",
                'res_model': 'df.geodynamics.plan.overlap.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': dict(self.env.context, default_task_ids=[(6, 0, tasks_with_overlap.ids)]),
            }

    def autoPlan(self):
        company, login, password = self._get_geodynamic_configs()

        gdHandler = GeodynamicsHandler(login, password, company, self.env)
        planDirect = self.env['ir.config_parameter'].sudo().get_param('geodynamics.plandirectly')

        if not planDirect or planDirect == 'False':
            return

        for record in self:
            _logger.debug('In autoplan, record: %s', record.id)
            if record.planned_date_start == False or record.date_deadline == False:
                _logger.debug('need return')
                return

            for pId in record.df_gd_planning_overlapped_ids:
                gdHandler.deletePlanning3(pId.id)



            _logger.debug('Calling task')
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
            _logger.debug('go')
            self.checkOverlap(record)

    def checkOverlap(self, sRecord):
        sErrors = []

        for wn in sRecord.df_employees_with_geodynamics_ids:
            _logger.debug('Examine... %s', wn.name)
            _logger.debug('Start: %s', sRecord.planned_date_start)
            _logger.debug('End: %s', sRecord.date_deadline)
            startOverlaps = self.env['df.geodynamics.planning'].search([('employee_id','=',wn.id),('start_datetime','>',sRecord.planned_date_start),('start_datetime', '<', sRecord.date_deadline),('task_id','!=',sRecord.id)])

            for s in startOverlaps:
                _logger.debug('%s', s.display_name_with_task)

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


    def _compute_task_create_action(self):
        """Decide what to do on task creation based solely on the creator's preference.
        Uses create_uid.df_task_create_action; defaults to 'add_poi' when unset/invalid.
        Returns: 'auto_plan' | 'add_poi' | 'none'
        """
        self.ensure_one()
        allowed = {'auto_plan', 'add_poi'}
        pref = (getattr(self.env.user, 'df_task_create_action', False) or 'add_poi')
        return pref if pref in allowed else 'add_poi'

    def create(self, vals):
        """Override create method to perform Geodynamics action based on user preference"""
        tasks = super(Project, self).create(vals)

        for task in tasks:
            action = task._compute_task_create_action()
            # Execute requested action with guards
            if action == 'add_poi':
                task.addPointOfTask(task)
            else:  # action == 'auto_plan'
                task.autoPlan()

        return tasks

    def addPointOfTask(self, task):
        if task.project_id:
            try:
                company, login, password = self._get_geodynamic_configs()

                if company and login and password:
                    gdHandler = GeodynamicsHandler(login, password, company, self.env)
                    result = gdHandler.addPoiFromTask(task)

                    if 'Success' in result:
                        # Extract POI ID from response and save it
                        poi_data = result['Success']
                        poi_id = poi_data['Id']
                        task.write({'df_geodynamics_poi_id': poi_id})
                        _logger.info(f"POI created successfully for task {task.id} with ID {poi_id}")

                    else:
                        _logger.warning(f"Failed to create POI for task {task.id}: {result}")
                else:
                    _logger.warning("Geodynamics configuration missing, skipping POI creation")

            except Exception as e:
                _logger.error(f"Error creating POI for task {task.id}: {str(e)}")
                # Don't fail task creation if POI creation fails
        else:
            _logger.info(f"Task {task.id} has no project_id, skipping POI creation")

    def write(self, vals):

        res = super(Project, self).write(vals)
        for task in self:
            action = task._compute_task_create_action()
            # Execute requested action with guards

            if action == 'add_poi':
                if task.df_geodynamics_poi_id:
                    task._check_and_update_geo_by_stage(vals)
                elif not task.stage_id.df_is_completion_stage and not task._has_change_stage_to_finished(vals):
                    # If no POI exists, create one
                    task.addPointOfTask(task)
            else:  # action == 'auto_plan'
                # Check if relevant fields are updated
                if 'planned_date_start' in vals or 'date_deadline' in vals or 'df_employee_ids' in vals:
                    # Make sure both dates exist before calling autoPlan
                    if task.planned_date_start and task.date_deadline:
                        task.autoPlan()
        return res

    def _has_change_stage_to_finished(self, vals):
        if 'stage_id' in vals:
            new_stage_id = vals['stage_id']
            new_stage = self.env['project.task.type'].browse(new_stage_id)
            if new_stage.df_is_completion_stage:
                return True
        return False

    def _check_and_update_geo_by_stage(self, vals):
        if 'stage_id' in vals:
            for rec in self:
                old_stage = rec.stage_id
                new_stage_id = vals['stage_id']
                new_stage = self.env['project.task.type'].browse(new_stage_id)

                # Check if moving to completion stage and has POI to delete
                if new_stage.df_is_completion_stage and rec.df_geodynamics_poi_id:
                    try:
                        company, login, password = self._get_geodynamic_configs()

                        if company and login and password:
                            gdHandler = GeodynamicsHandler(login, password, company, self.env)
                            result = gdHandler.deletePoi(rec.df_geodynamics_poi_id)

                            if 'Success' in result:
                                # Clear the POI ID after successful deletion
                                rec.df_geodynamics_poi_id = False
                                _logger.info(
                                    f"POI {rec.df_geodynamics_poi_id} deleted successfully for completed task {rec.id}")
                            else:
                                _logger.error(
                                    f"Failed to delete POI {rec.df_geodynamics_poi_id} for task {rec.id}: {result}")
                        else:
                            _logger.warning("Geodynamics configuration missing, cannot delete POI")

                    except Exception as e:
                        _logger.error(f"Error deleting POI for task {rec.id}: {str(e)}")

    def _get_geodynamic_configs(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')
        return company, login, password

    def _get_allowed_event_types(self):
        codes_str = self.env['ir.config_parameter'].sudo().get_param('geodynamics.import_event_types', '')
        if not codes_str:
            return None
        return set(c.strip() for c in codes_str.split(',') if c.strip())

    def _resolve_fleet_vehicle(self, resource_id):
        if not resource_id:
            return False
        vehicle = self.env['fleet.vehicle'].search([('df_geodynamics_id', '=', resource_id)], limit=1)
        return vehicle.id if vehicle else False

    def _gd_notify(self, title, ntype, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title, 'type': ntype, 'message': message, 'sticky': True,
                # Reload the current view after the notification so freshly created
                # timesheet lines appear without a manual page refresh.
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _gd_verbose_enabled(self):
        """True when 'Verbose Logging' is enabled in the Geodynamics settings."""
        return self.env['ir.config_parameter'].sudo().get_param(
            'geodynamics.verbose_logging', 'False').lower() in ('true', '1', 'yes')

    def _process_postcalc_data(self, data, record, emp, sDate, postcalcsource, allowed_types, filter_by_job=True,
                               expected_key=None, expected_id=None):
        """Create 'Registratie Geodynamics' timesheet lines from post-calc data.

        Returns (created_count, seen_keys) where seen_keys are the JobNumber /
        CostCenter values encountered (used for diagnostics when nothing matches).

        Which events are imported is controlled by the 'Event Types to Import'
        setting (allowed_types): timesheet events are filtered on their Type field
        (df_codes: 1=Activity, 5=Work, ...); empty means import all types.

        expected_key / expected_id override what the job filter matches against
        (defaults to record.df_gd_name / record.id). This lets the project-level
        fetch reuse this method with the project key ("<name>-P<id>", id "P<id>").
        """
        created = 0
        seen_keys = set()
        skipped_types = set()  # event Types that matched the key but are not in the Event Types filter
        expected = (expected_key if expected_key is not None else (record.df_gd_name or '')).strip().lower()
        task_id_str = str(expected_id if expected_id is not None else record.id)
        verbose = self._gd_verbose_enabled()
        entries = data.get("Data", []) if isinstance(data, dict) else []
        _logger.info('[Geodynamics][Postcalc] task=%s emp=%s date=%s source=%s filter_by_job=%s allowed_types=%s -> %d data entr(ies)',
                     record.id, emp.name, sDate, postcalcsource, filter_by_job, allowed_types, len(entries))
        if verbose:
            try:
                _logger.info('[Geodynamics][Postcalc][VERBOSE] raw response for emp=%s date=%s:\n%s',
                             emp.name, sDate, json.dumps(data, indent=2, default=str))
            except Exception:
                _logger.info('[Geodynamics][Postcalc][VERBOSE] raw response for emp=%s date=%s: %s', emp.name, sDate, data)
        for entry in entries:
            _ts = entry.get("TimesheetEvents", []) or entry.get("TimeSheetEvents", []) or []
            _pc = entry.get("PostCalculationEvents", []) or []
            _logger.info('[Geodynamics][Postcalc]   entry: %d TimesheetEvents, %d PostCalculationEvents; CostCenterFullCodes=%s JobNumbers=%s',
                         len(_ts), len(_pc),
                         [e.get('CostCenterFullCode') or e.get('CostCenter') for e in _pc][:15],
                         [e.get('JobNumber') for e in _ts][:15])
            if postcalcsource == 'timesheet':
                events = entry.get("TimesheetEvents", []) or entry.get("TimeSheetEvents", []) or []
                _logger.info('[Geodynamics][Postcalc]   processing %d TimesheetEvents', len(events))
                for event in events:
                    ev_type = event.get('Type')
                    jobnr = (event.get('JobNumber') or '').strip()
                    if jobnr:
                        seen_keys.add(jobnr)
                    if verbose:
                        _logger.info('[Geodynamics][Postcalc][VERBOSE]     TimesheetEvent: %s', event)
                    # 1) Match this task/project by key (trailing "-<id>" segment).
                    job_id = jobnr.rsplit('-', 1)[-1].strip() if '-' in jobnr else ''
                    job_matches = jobnr.lower() == expected or (job_id and job_id == task_id_str)
                    if filter_by_job and not job_matches:
                        _logger.info('[Geodynamics][Postcalc]     SKIP JobNumber=%r (id=%r): expected %r (id %s)',
                                     jobnr, job_id, expected, task_id_str)
                        continue
                    # 2) Apply the 'Event Types to Import' setting (res.config.settings)
                    #    on the event Type (df_codes: 1=Activity, 5=Work, ...). Empty = all.
                    if allowed_types and str(ev_type) not in allowed_types:
                        skipped_types.add(ev_type)
                        _logger.info('[Geodynamics][Postcalc]     SKIP Type=%s: not in Event Types to Import %s', ev_type, sorted(allowed_types))
                        continue
                    try:
                        duration = self.calculate_time_difference(event['StartDateTimeLocal'], event['StopDateTimeLocal'])
                        if duration['diff'] <= 0:
                            _logger.info('[Geodynamics][Postcalc]     SKIP zero-duration TimesheetEvent JobNumber=%r', jobnr)
                            continue
                        vals = {
                            'account_id': record.project_id.account_id.id, 'date': sDate,
                            'task_id': record.id, 'employee_id': emp.id,
                            'name': 'Registratie Geodynamics',
                            'df_gd_type': str(event.get('Type', '')), 'df_gd_eventtype': str(event.get('EventType', '')),
                            'df_start_time': duration['start'], 'df_end_time': duration['stop'], 'unit_amount': duration['diff'],
                        }
                        start_loc = event.get('StartLocation')
                        if start_loc and start_loc.get('AddressLine'):
                            vals['df_gd_start_location'] = start_loc['AddressLine']
                        stop_loc = event.get('StopLocation')
                        if stop_loc and stop_loc.get('AddressLine'):
                            vals['df_gd_stop_location'] = stop_loc['AddressLine']
                        mileage = event.get('Mileage')
                        if mileage is not None:
                            vals['df_gd_mileage'] = float(mileage)
                        start_res = event.get('StartResource') or {}
                        start_res_id = start_res.get('Id') if isinstance(start_res, dict) else event.get('StartResourceId')
                        stop_res = event.get('StopResource') or {}
                        stop_res_id = stop_res.get('Id') if isinstance(stop_res, dict) else event.get('StopResourceId')
                        fleet_start = self._resolve_fleet_vehicle(start_res_id)
                        fleet_stop = self._resolve_fleet_vehicle(stop_res_id)
                        if fleet_start:
                            vals['df_gd_start_resource_id'] = fleet_start
                        if fleet_stop:
                            vals['df_gd_stop_resource_id'] = fleet_stop
                        self.env['account.analytic.line'].create(vals)
                        created += 1
                        _logger.info('[Geodynamics][Postcalc]     CREATED %.2fh JobNumber=%r', duration['diff'], jobnr)
                    except Exception as e:
                        _logger.exception('[Geodynamics][Postcalc]     ERROR creating line for event %s: %s', event, e)
            elif postcalcsource == 'postcalculation':
                events = entry.get("PostCalculationEvents", [])
                _logger.info('[Geodynamics][Postcalc]   entry with %d PostCalculationEvents', len(events))
                for event in events:
                    ev_type = event.get('EventType')
                    # Geodynamics splits the pushed ActivityNumber "name-<id>" into
                    # CostCenter (name) + ActivityCode (id). Match on the clean
                    # ActivityCode to avoid separator/whitespace differences in the
                    # reconstructed CostCenterFullCode.
                    activity_code = str(event.get('ActivityCode') or '').strip()
                    cc_full = (event.get('CostCenterFullCode') or event.get('CostCenter') or '').strip()
                    if cc_full or activity_code:
                        seen_keys.add(cc_full or activity_code)
                    if verbose:
                        _logger.info('[Geodynamics][Postcalc][VERBOSE]     PostCalculationEvent: %s', event)
                    # 1) Match this task/project by key.
                    cc_matches = (activity_code and activity_code == task_id_str) or (cc_full and cc_full.lower() == expected)
                    if filter_by_job and not cc_matches:
                        _logger.info('[Geodynamics][Postcalc]     SKIP CostCenterFullCode=%r ActivityCode=%r: expected %r (id %s)',
                                     cc_full, activity_code, record.df_gd_name, task_id_str)
                        continue
                    # 2) Apply the 'Event Types to Import' setting on EventType. PostCalculation
                    #    events may carry no EventType, so only filter when one is present.
                    if allowed_types and ev_type is not None and str(ev_type) not in allowed_types:
                        skipped_types.add(ev_type)
                        _logger.info('[Geodynamics][Postcalc]     SKIP EventType=%s: not in Event Types to Import %s', ev_type, sorted(allowed_types))
                        continue
                    try:
                        duration = self.calculate_time_difference(event['TimeFromLocal'], event['TimeToLocal'])
                        if duration['diff'] <= 0:
                            _logger.info('[Geodynamics][Postcalc]     SKIP zero-duration PostCalculationEvent key=%r', cc_full or activity_code)
                            continue
                        vals = {
                            'account_id': record.project_id.account_id.id, 'date': sDate,
                            'task_id': record.id, 'employee_id': emp.id,
                            'name': 'Registratie Geodynamics',
                            'df_start_time': duration['start'], 'df_end_time': duration['stop'], 'unit_amount': duration['diff'],
                        }
                        if ev_type is not None:
                            vals['df_gd_eventtype'] = str(ev_type)
                        mobility = event.get('Mobility')
                        if mobility:
                            total_km = (mobility.get('KmDriver', 0) or 0) + (mobility.get('KmPassenger', 0) or 0) + (mobility.get('KmSingleDriver', 0) or 0)
                            if total_km:
                                vals['df_gd_mileage'] = total_km
                        self.env['account.analytic.line'].create(vals)
                        created += 1
                        _logger.info('[Geodynamics][Postcalc]     CREATED %.2fh key=%r', duration['diff'], cc_full or activity_code)
                    except Exception as e:
                        _logger.exception('[Geodynamics][Postcalc]     ERROR creating line for event %s: %s', event, e)
            else:
                _logger.warning('[Geodynamics][Postcalc]   Unknown postcalcsource=%r -> no events processed', postcalcsource)
        return created, seen_keys, skipped_types

    def laadPostcalc(self):
        company, login, password = self._get_geodynamic_configs()
        # Fall back to the historical default when the setting was never saved
        # (the Post-calculation Source setting is currently hidden in the UI).
        postcalcsource = self.env['ir.config_parameter'].sudo().get_param('geodynamics.postcalcsource') or 'postcalculation'
        allowed_types = self._get_allowed_event_types()
        raw_event_types = self.env['ir.config_parameter'].sudo().get_param('geodynamics.import_event_types', '')
        _logger.info('[Geodynamics][Postcalc] Event Types to Import (from res.config.settings): raw=%r -> %s | source=%s',
                     raw_event_types, sorted(allowed_types) if allowed_types else '(empty = all types)', postcalcsource)

        if not (company and login and password):
            _logger.warning('[Geodynamics][Postcalc] Missing credentials (company=%s login=%s password set=%s)',
                            bool(company), bool(login), bool(password))
            return self._gd_notify('Geodynamics', 'danger', 'Geodynamics credentials ontbreken in de instellingen.')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        total_created = 0
        data_returned = False
        seen_keys = set()
        skipped_types = set()

        for record in self:
            _logger.info('[Geodynamics][Postcalc] === Task %s "%s" df_gd_name=%r source=%s allowed_types=%s ===',
                         record.id, record.name, record.df_gd_name, postcalcsource, allowed_types)
            if record.df_gd_planning_ids2:
                _logger.info('[Geodynamics][Postcalc] Using %d planning item(s)', len(record.df_gd_planning_ids2))
                for it in record.df_gd_planning_ids2:
                    if not it.employee_id.df_geodynamics_id:
                        _logger.info('[Geodynamics][Postcalc] SKIP planning: employee %s has no Geodynamics id', it.employee_id.name)
                        continue
                    sDate = it.start_datetime.date()
                    _logger.info('[Geodynamics][Postcalc] Fetch emp=%s (gd=%s) date=%s',
                                 it.employee_id.name, it.employee_id.df_geodynamics_id, sDate)
                    data = gdHandler.laadPostcalc(it.employee_id.df_geodynamics_id, self.date_to_datetime(sDate, 0, 0))
                    if isinstance(data, dict) and data.get('Data'):
                        data_returned = True
                    else:
                        _logger.info('[Geodynamics][Postcalc] No data returned by API for emp=%s date=%s (raw=%s)',
                                     it.employee_id.name, sDate, data)

                    self.env['account.analytic.line'].search([
                        ('account_id', '=', record.project_id.account_id.id),
                        ('date', '=', sDate),
                        ('task_id', '=', record.id),
                        ('employee_id', '=', it.employee_id.id),
                    ]).unlink()

                    created, keys, sk = self._process_postcalc_data(data, record, it.employee_id, sDate, postcalcsource, allowed_types, filter_by_job=True)
                    total_created += created
                    seen_keys |= keys
                    skipped_types |= sk
            else:
                employees = record.df_employee_ids or record.project_id.df_gd_employee_ids
                employees = employees.filtered(lambda e: e.df_geodynamics_id)
                if not employees:
                    _logger.warning('[Geodynamics][Postcalc] Task %s: no employees with Geodynamics ID found', record.id)
                    continue
                _logger.info('[Geodynamics][Postcalc] No planning items; using %d employee(s) over date range', len(employees))
                start_date = record.planned_date_start.date() if record.planned_date_start else fields.Date.context_today(self)
                end_date = record.date_deadline.date() if record.date_deadline else start_date
                current_date = start_date
                while current_date <= end_date:
                    for emp in employees:
                        _logger.info('[Geodynamics][Postcalc] Fetch emp=%s (gd=%s) date=%s', emp.name, emp.df_geodynamics_id, current_date)
                        data = gdHandler.laadPostcalc(emp.df_geodynamics_id, self.date_to_datetime(current_date, 0, 0))
                        if isinstance(data, dict) and data.get('Data'):
                            data_returned = True
                        else:
                            _logger.info('[Geodynamics][Postcalc] No data returned by API for emp=%s date=%s (raw=%s)',
                                         emp.name, current_date, data)

                        self.env['account.analytic.line'].search([
                            ('account_id', '=', record.project_id.account_id.id),
                            ('date', '=', current_date),
                            ('task_id', '=', record.id),
                            ('employee_id', '=', emp.id),
                        ]).unlink()

                        created, keys, sk = self._process_postcalc_data(data, record, emp, current_date, postcalcsource, allowed_types, filter_by_job=False)
                        total_created += created
                        seen_keys |= keys
                        skipped_types |= sk
                    current_date += timedelta(days=1)

        _logger.info('[Geodynamics][Postcalc] DONE: %d line(s) created, data_returned=%s, keys seen=%s, expected=%s',
                     total_created, data_returned, sorted(seen_keys), self.mapped('df_gd_name'))

        if total_created:
            return self._gd_notify('Geodynamics Post-calculatie', 'success',
                                   '%d Registratie Geodynamics regel(s) aangemaakt.' % total_created)
        if skipped_types:
            return self._gd_notify(
                'Geodynamics Post-calculatie', 'warning',
                'Geen registraties aangemaakt. Er zijn events gevonden voor deze taak, maar hun type (%s) '
                'staat niet in "Event Types to Import" (%s).\nPas de instelling aan in de Geodynamics-instellingen.'
                % (', '.join(sorted(str(t) for t in skipped_types)),
                   ', '.join(sorted(allowed_types)) if allowed_types else '(leeg)'))
        if data_returned and seen_keys:
            return self._gd_notify(
                'Geodynamics Post-calculatie', 'warning',
                'Geen registraties aangemaakt. Er zijn wel post-calculatie events gevonden, maar de '
                'kostenplaats/jobnummer kwam niet overeen met de taak.\nGevonden: %s\nVerwacht: %s\n'
                'Herplan de taak zodat het ActivityNumber in Geodynamics overeenkomt.'
                % (', '.join(sorted(seen_keys)), ', '.join(self.mapped('df_gd_name'))))
        return self._gd_notify(
            'Geodynamics Post-calculatie', 'warning',
            'Geen post-calculatie data gevonden in Geodynamics voor deze taak/periode. '
            'Mogelijk hebben de werknemers nog geen tijd geregistreerd in Geodynamics.')

    def fetchClockings(self):
        """Fetch clockings for each linked employee (hr.employee) on the task within its date range.
        Date range logic:
          from = planned_date_start 00:00:00 (or today 00:00:00 if missing)
          to   = date_deadline       23:59:59 (or planned_date_start / today if missing)
        Computes total active hours (Geodynamics clockings using DateTimeLocal) and
        writes per-day aggregated account.analytic.line rows for this task.
        When project name contains job code patterns (S\d{5}), only clockings whose JobNumber prefix
        matches one of those codes are considered.
        """
        company, login, password = self._get_geodynamic_configs()
        if not (company and login and password):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Geodynamics',
                    'message': 'Missing Geodynamics credentials in Settings.',
                    'type': 'danger',
                    'sticky': False,
                }
            }
        handler = GeodynamicsHandler(login, password, company, self.env)
        total_calls = 0
        total_records = 0
        total_active_minutes = 0
        created_lines = 0
        updated_lines = 0

        def _split_interval_by_day(start_dt, end_dt):
            """Split an interval across days returning list[(date, minutes)]"""
            results = []
            cur_start = start_dt
            # iterate until same date
            while cur_start.date() < end_dt.date():
                day_end = datetime.combine(cur_start.date(), datetime.min.time()).replace(hour=23, minute=59, second=59)
                minutes = int((day_end - cur_start).total_seconds() // 60) + 1
                if minutes > 0:
                    results.append((cur_start.date(), minutes))
                cur_start = day_end + timedelta(seconds=1)
            minutes_last = int((end_dt - cur_start).total_seconds() // 60)
            if minutes_last > 0:
                results.append((cur_start.date(), minutes_last))
            return results

        for task in self:
            if not (task.project_id and task.project_id.account_id):
                continue
            # date range
            start_date = task.planned_date_start.date() if task.planned_date_start else fields.Date.context_today(self)
            end_date = (task.date_deadline.date() if task.date_deadline else (task.planned_date_start.date() if task.planned_date_start else fields.Date.context_today(self)))
            if end_date < start_date:
                end_date = start_date
            from_dt_str = f"{start_date} 00:00:00"
            to_dt_str = f"{end_date} 23:59:59"
            job_codes = task._extract_project_job_codes()
            _logger.debug('[Geodynamics][Task] %s job_codes=%s range=%s..%s employees=%d', task.id, list(job_codes), from_dt_str, to_dt_str, len(task.df_employee_ids))
            per_day_minutes = {}
            for emp in task.df_employee_ids:
                if not emp.df_geodynamics_id:
                    continue
                resp = handler.getClockingsByUserDateRange(emp.df_geodynamics_id, from_dt_str, to_dt_str)
                if not resp.get('Success'):
                    _logger.warning('[Geodynamics][Task] fetch failed emp=%s (%s): %s', emp.id, emp.name, resp.get('Error'))
                    continue
                total_calls += 1
                total_records += resp.get('Count', 0)
                raw_records = resp.get('Data') or []
                # Filter by job code BEFORE computing durations
                if job_codes:
                    filtered_records = []
                    for rec in raw_records:
                        if not isinstance(rec, dict):
                            continue
                        job_raw = rec.get('JobNumber') or rec.get('JobNumberFull') or rec.get('ActivityNumber')
                        token = task._normalize_job_number_token(job_raw)
                        if token and token in job_codes:
                            filtered_records.append(rec)
                    _logger.debug('[Geodynamics][Task] Emp %s job-filter raw=%d -> kept=%d', emp.id, len(raw_records), len(filtered_records))
                else:
                    filtered_records = raw_records
                if not filtered_records:
                    continue
                durations = handler.compute_clocking_activity_durations(filtered_records)
                intervals = durations.get('intervals', [])
                emp_minutes_added = 0
                for interval in intervals:
                    s = interval.get('start')
                    e = interval.get('end')
                    if not (s and e):
                        continue
                    if isinstance(s, str):
                        try:
                            s = datetime.fromisoformat(s)
                        except Exception:
                            continue
                    if isinstance(e, str):
                        try:
                            e = datetime.fromisoformat(e)
                        except Exception:
                            continue
                    minutes_val = interval.get('minutes', 0)
                    if minutes_val <= 0:
                        continue
                    emp_minutes_added += minutes_val
                    if s.date() == e.date():
                        key = (emp.id, s.date())
                        per_day_minutes[key] = per_day_minutes.get(key, 0) + minutes_val
                    else:
                        for ddt, mins in _split_interval_by_day(s, e):
                            key = (emp.id, ddt)
                            per_day_minutes[key] = per_day_minutes.get(key, 0) + mins
                total_active_minutes += emp_minutes_added
                _logger.debug('[Geodynamics][Task] Emp %s minutes_added=%d intervals=%d', emp.id, emp_minutes_added, len(intervals))
            # write timesheet lines
            for (emp_id, ddate), minutes in per_day_minutes.items():
                hours = round(minutes / 60.0, 2)
                if hours <= 0:
                    continue
                domain = [
                    ('account_id', '=', task.project_id.account_id.id),
                    ('employee_id', '=', emp_id),
                    ('date', '=', ddate),
                    ('task_id', '=', task.id)
                ]
                line = self.env['account.analytic.line'].search(domain, limit=1)
                if line:
                    line.write({'unit_amount': hours})
                    updated_lines += 1
                else:
                    self.env['account.analytic.line'].create({
                        'account_id': task.project_id.account_id.id,
                        'date': ddate,
                        'task_id': task.id,
                        'employee_id': emp_id,
                        'name': 'Registratie Geodynamics',
                        'unit_amount': hours,
                    })
                    created_lines += 1
        total_active_hours = round(total_active_minutes / 60.0, 2)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Geodynamics',
                'message': f'Fetched clockings (tasks): employees {total_calls}, records {total_records}, active hours {total_active_hours}, timesheets +{created_lines}/~{updated_lines}.',
                'type': 'success',
                'sticky': False,
            }
        }

    def _extract_project_job_codes(self):
        """Extract job codes (pattern S\d{5}) from related project name."""
        self.ensure_one()
        if not self.project_id or not self.project_id.name:
            return set()
        name = self.project_id.name.upper()
        return set(re.findall(r'S\d{5}', name))

    def _normalize_job_number_token(self, raw):
        if not raw:
            return None
        token = raw.split(' - ')[0].strip().upper()
        m = re.match(r'^(S\d+)$', token)
        return m.group(1) if m else None
