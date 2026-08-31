# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
import logging

from odoo import models, fields, api

from . import gdhandler
from .gdhandler import GeodynamicsHandler
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

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
    df_planning_slot_id = fields.Many2one(
        comodel_name='planning.slot', string='Planning shift',
        ondelete='set null', index=True, copy=False,
        help='Shift in the Odoo Planning app kept in sync with this Geodynamics planning. '
             'Deleting either one deletes the other.')
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


    # ------------------------------------------------------------------
    # Odoo Planning app synchronisation
    #
    # Every planning sent to Geodynamics gets a matching shift in the Odoo
    # Planning app (planning.slot), and deleting either side deletes the other,
    # so both stay in sync at all times. The user is always warned about the
    # counterpart being created or deleted.
    #
    # 'gd_skip_planning_sync' in the context marks the half of a delete that is
    # already being handled, so the two unlink() overrides do not call each other
    # back and forth.
    # ------------------------------------------------------------------

    def _gd_slot_vals(self):
        """Values for the planning.slot counterpart of this Geodynamics planning."""
        self.ensure_one()
        employee = self.employee_id or self.user_id.employee_id
        vals = {
            'start_datetime': self.start_datetime,
            'end_datetime': self.end_datetime,
            'resource_id': employee.resource_id.id,
            'project_id': self.project_id.id or self.task_id.project_id.id,
            'task_id': self.task_id.id,
            'name': self.description or self.activitynumber,
            'company_id': employee.company_id.id or self.env.company.id,
        }
        # planning.slot carries different fields depending on the Odoo version and
        # on which Planning bridges are installed, so only keep what this database
        # actually has (an unknown key would make create() fail).
        slot_fields = self.env['planning.slot']._fields
        return {key: value for key, value in vals.items() if key in slot_fields and value}

    def _gd_sync_create_slots(self):
        """Create the Planning app shift for plannings that do not have one yet."""
        if self.env.context.get('gd_skip_planning_sync'):
            return
        Slot = self.env['planning.slot']
        synced = self.browse()
        failed = self.browse()
        for planning in self:
            if planning.df_planning_slot_id or not (planning.start_datetime and planning.end_datetime):
                continue
            try:
                # A savepoint keeps a rejected shift from poisoning the transaction that
                # is storing the plannings; the planning itself must survive, since it
                # already exists in Geodynamics by the time we get here.
                with self.env.cr.savepoint():
                    # sudo: the planner sending work to Geodynamics does not necessarily
                    # have write access to the Planning app.
                    slot = Slot.sudo().with_context(gd_skip_planning_sync=True).create(
                        planning._gd_slot_vals())
                planning.df_planning_slot_id = slot.id
                synced |= planning
            except Exception:
                _logger.exception('[Geodynamics][Planning] Could not create the Planning app shift for planning %s',
                                  planning.id)
                failed |= planning
        if synced:
            synced._gd_notify_counterpart('created')
        if failed:
            failed._gd_notify_counterpart('create_failed')

    def _gd_sync_unlink_slots(self):
        """Delete the Planning app shifts of these plannings."""
        if self.env.context.get('gd_skip_planning_sync'):
            return
        slots = self.df_planning_slot_id
        if not slots:
            return
        # Warn first: once the records are gone their names cannot be read anymore.
        self.filtered('df_planning_slot_id')._gd_notify_counterpart('slot_deleted')
        slots.sudo().with_context(gd_skip_planning_sync=True).unlink()

    def _gd_notify_counterpart(self, action):
        """Warn the user that the counterpart of these plannings was created/deleted."""
        if not self:
            return
        headers = {
            'created': ('Planning shift created', 'Also created in the Planning app:'),
            'slot_deleted': ('Planning shift deleted', 'Also deleted from the Planning app:'),
            'gd_deleted': ('Geodynamics planning deleted', 'Also deleted from Geodynamics:'),
            'create_failed': ('No Planning shift created',
                              'These plannings were sent to Geodynamics, but no shift could be '
                              'created in the Planning app (see the server log):'),
        }
        title, intro = headers[action]
        message = '%s\n%s' % (intro, '\n'.join(planning.display_name for planning in self))
        self.env['bus.bus'].sudo()._sendone(
            self.env.user.partner_id, 'simple_notification',
            {'type': 'warning' if action == 'create_failed' else 'info',
             'title': title, 'message': message, 'sticky': action == 'create_failed'},
        )

    @api.model_create_multi
    def create(self, vals_list):
        plannings = super().create(vals_list)
        plannings._gd_sync_create_slots()
        return plannings

    def write(self, vals):
        """Keep the Planning app shift on the same period / employee as the planning."""
        result = super().write(vals)
        tracked = {'start_datetime', 'end_datetime', 'employee_id', 'user_id', 'description'}
        if tracked.intersection(vals) and not self.env.context.get('gd_skip_planning_sync'):
            for planning in self:
                slot = planning.df_planning_slot_id
                if slot:
                    slot.sudo().with_context(gd_skip_planning_sync=True).write(planning._gd_slot_vals())
        return result

    def unlink(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')

        gdHandler = GeodynamicsHandler(login, password, company, self.env)

        for record in self:
            if record.id_geodynamics:
                gdHandler.removePlanning(record.id_geodynamics)

        # Keep the Planning app in sync: the shifts go with the plannings.
        self._gd_sync_unlink_slots()

        return super(GeodynamicsPlanning, self).unlink()

    def removePlanning(self):
        self.unlink()
