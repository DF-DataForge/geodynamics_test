# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api

class AccAnalLine(models.Model):
    _inherit = 'account.analytic.line'

    df_start_time = fields.Datetime(string='Starttijd')
    df_end_time = fields.Datetime(string='Eindtijd')

    df_gd_type = fields.Selection(
        [('0', 'Absence'), ('1', 'Activity'), ('2', 'Allowance'), ('3', 'Break'), ('4', 'Movement'), ('5', 'Work'), ('6', 'Error'),
         ('7', 'Unpaid'), ('8', 'TravelTime'), ('9', 'External')], string='Event Geodynamics')

    df_gd_eventtype = fields.Selection([
        ('0', 'Absence paid'),
        ('1', 'Absence unpaid'),
        ('2', 'Activity'),
        ('3', 'Break'),
        ('4', 'Movement driver'),
        ('5', 'Movement passenger'),
        ('6', 'Movement single driver'),
        ('7', 'Work'),
        ('8', 'Load/Unload'),
        ('9', 'Travel time'),
        ('10', 'External'),
        ('11', 'Unpaid'),
        ('12', 'Allowance'),
        ('13', 'Error')
    ], string="Event type Geodynamics")

    df_gd_start_location = fields.Char(string='Startlocatie')
    df_gd_stop_location = fields.Char(string='Stoplocatie')
    df_gd_mileage = fields.Float(string='Kilometerstand', digits=(10, 1))
    df_gd_start_resource_id = fields.Many2one('fleet.vehicle', string='Start voertuig')
    df_gd_stop_resource_id = fields.Many2one('fleet.vehicle', string='Stop voertuig')

    df_gd_event_type_id = fields.Many2one(
        'df.geodynamics.event.type', string='Geodynamics event type',
        index=True, ondelete='set null',
        help='Geodynamics event type this line was imported from. Its "Log hours as cost" flag '
             'decides whether the hours are charged to the project.')

    # --- Cost of imported Geodynamics hours ---------------------------------
    #
    # Every imported event becomes a timesheet line ('urenstaat') on the task, but
    # only event types with "Log hours as cost" ticked may add cost to the project.
    # For the others we keep unit_amount (the hours) and drop the analytic amount
    # (the cost hr_timesheet derives from the employee hourly cost).

    def _df_gd_skip_cost(self):
        """True when this line's Geodynamics event type must not be charged."""
        self.ensure_one()
        event_type = self.df_gd_event_type_id
        return bool(event_type) and not event_type.df_log_timesheets

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        # hr_timesheet fills in the cost after the record exists, so clear it here.
        # Writing 'amount' on its own does not trigger a new cost computation.
        to_zero = lines.filtered(lambda l: l._df_gd_skip_cost() and l.amount)
        if to_zero:
            # sudo: correcting the cost of lines we just created, which may belong to
            # another employee than the user running the Geodynamics import.
            to_zero.sudo().write({'amount': 0.0})
        return lines

    def _timesheet_postprocess_values(self, values):
        """Keep the hours but zero the cost for event types that must not be charged.

        Called by hr_timesheet whenever the hours, employee or analytic account of a
        timesheet line change, so an edit does not bring the cost back.
        """
        result = super()._timesheet_postprocess_values(values)
        for line in self:
            line_vals = result.get(line.id)
            if line_vals and 'amount' in line_vals and line._df_gd_skip_cost():
                line_vals['amount'] = 0.0
        return result
