# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo.tests.common import TransactionCase


class TestEventTypeLogCost(TransactionCase):
    """Imported hours are always timesheets; only event types with
    'Log hours as cost' (df_log_timesheets) add cost to the project."""

    def setUp(self):
        super().setUp()
        self.EventType = self.env['df.geodynamics.event.type']
        self.AnalyticLine = self.env['account.analytic.line']

        self.paid_type = self._event_type('5', 'Work', True)
        self.unpaid_type = self._event_type('3', 'Break', False)

        employee_vals = {'name': 'GD Cost Tester'}
        # hourly_cost is the timesheet cost field; older versions name it timesheet_cost.
        cost_field = 'hourly_cost' if 'hourly_cost' in self.env['hr.employee']._fields else 'timesheet_cost'
        employee_vals[cost_field] = 40.0
        self.employee = self.env['hr.employee'].create(employee_vals)

        self.project = self.env['project.project'].create({
            'name': 'GD Cost Project',
            'allow_timesheets': True,
        })
        self.task = self.env['project.task'].create({
            'name': 'Registratie Geodynamics',
            'project_id': self.project.id,
        })

    def _event_type(self, code, name, log_timesheets):
        """Return the event type for `code`, with df_log_timesheets forced."""
        event_type = self.EventType.search([('df_code', '=', code)], limit=1)
        if not event_type:
            event_type = self.EventType.create({'name': name, 'df_code': code})
        event_type.df_log_timesheets = log_timesheets
        return event_type

    def _create_line(self, event_type, hours=2.0):
        return self.AnalyticLine.create({
            'name': 'Registratie Geodynamics',
            'project_id': self.project.id,
            'task_id': self.task.id,
            'employee_id': self.employee.id,
            'unit_amount': hours,
            'df_gd_event_type_id': event_type.id,
        })

    # ------------------------------------------------------------------
    # Cost of imported hours
    # ------------------------------------------------------------------

    def test_flag_on_keeps_cost(self):
        line = self._create_line(self.paid_type)
        self.assertEqual(line.unit_amount, 2.0, 'hours must be logged as a timesheet')
        self.assertNotEqual(line.amount, 0.0, 'a ticked event type must be charged to the project')

    def test_flag_off_keeps_hours_without_cost(self):
        line = self._create_line(self.unpaid_type)
        self.assertEqual(line.unit_amount, 2.0, 'hours must still be logged as a timesheet')
        self.assertEqual(line.amount, 0.0, 'an unticked event type must not add cost to the project')

    def test_flag_off_stays_free_after_edit(self):
        line = self._create_line(self.unpaid_type)
        line.write({'unit_amount': 5.0})
        self.assertEqual(line.unit_amount, 5.0)
        self.assertEqual(line.amount, 0.0, 'editing the hours must not bring the cost back')

    def test_line_without_event_type_is_untouched(self):
        line = self.AnalyticLine.create({
            'name': 'Manual entry',
            'project_id': self.project.id,
            'task_id': self.task.id,
            'employee_id': self.employee.id,
            'unit_amount': 2.0,
        })
        self.assertFalse(line.df_gd_event_type_id)
        self.assertNotEqual(line.amount, 0.0, 'non-Geodynamics timesheets keep the standard cost')

    # ------------------------------------------------------------------
    # Event type lookup used by the post-calculation import
    # ------------------------------------------------------------------

    def test_code_map_resolves_codes(self):
        code_map = self.EventType._code_map()
        self.assertEqual(code_map.get('5'), self.paid_type)
        self.assertEqual(code_map.get('3'), self.unpaid_type)
        self.assertIsNone(code_map.get('999'), 'unknown codes must not resolve to an event type')
