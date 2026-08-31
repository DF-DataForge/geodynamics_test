# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from datetime import datetime
from unittest.mock import patch

from odoo.tests.common import TransactionCase

REMOVE_PLANNING = 'odoo.addons.geodynamics.models.gdhandler.GeodynamicsHandler.removePlanning'


class TestPlanningSlotSync(TransactionCase):
    """Two-way sync between df.geodynamics.planning and the Planning app (planning.slot)."""

    def setUp(self):
        super().setUp()
        self.Planning = self.env['df.geodynamics.planning']
        self.Slot = self.env['planning.slot']
        self.employee = self.env['hr.employee'].create({'name': 'GD Sync Employee'})
        self.project = self.env['project.project'].create({'name': 'GD Sync Project'})
        self.task = self.env['project.task'].create({
            'name': 'GD Sync Task',
            'project_id': self.project.id,
        })
        self.start = datetime(2026, 6, 1, 8, 0, 0)
        self.stop = datetime(2026, 6, 1, 16, 0, 0)

    def _create_planning(self, **overrides):
        vals = {
            'start_datetime': self.start,
            'end_datetime': self.stop,
            'id_geodynamics': 'gd-planning-1',
            'employee_id': self.employee.id,
            'task_id': self.task.id,
            'project_id': self.project.id,
            'activitynumber': 'ACT-001',
            'description': 'Sync me',
        }
        vals.update(overrides)
        return self.Planning.create(vals)

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def test_create_planning_creates_slot(self):
        planning = self._create_planning()
        slot = planning.df_planning_slot_id
        self.assertTrue(slot, 'Creating a planning must create a Planning app shift')
        self.assertEqual(slot.start_datetime, self.start)
        self.assertEqual(slot.end_datetime, self.stop)
        self.assertEqual(slot.resource_id, self.employee.resource_id)

    def test_slot_links_back_to_planning(self):
        planning = self._create_planning()
        self.assertIn(planning, planning.df_planning_slot_id.df_gd_planning_ids)

    def test_slot_creation_is_one_directional(self):
        """A shift created by hand in the Planning app must not create a planning."""
        slot = self.Slot.create({
            'start_datetime': self.start,
            'end_datetime': self.stop,
            'resource_id': self.employee.resource_id.id,
        })
        self.assertFalse(slot.df_gd_planning_ids)

    # ------------------------------------------------------------------
    # Deletion, both ways
    # ------------------------------------------------------------------

    def test_delete_planning_deletes_slot(self):
        with patch(REMOVE_PLANNING, return_value=True) as remove:
            planning = self._create_planning()
            slot = planning.df_planning_slot_id
            planning.unlink()
        self.assertFalse(slot.exists(), 'Deleting a planning must delete its shift')
        remove.assert_called_once_with('gd-planning-1')

    def test_delete_slot_deletes_planning_and_calls_api(self):
        with patch(REMOVE_PLANNING, return_value=True) as remove:
            planning = self._create_planning()
            slot = planning.df_planning_slot_id
            slot.unlink()
        self.assertFalse(planning.exists(), 'Deleting a shift must delete its Geodynamics planning')
        remove.assert_called_once_with('gd-planning-1')

    def test_delete_does_not_recurse(self):
        """Neither unlink() override may call the other one back."""
        with patch(REMOVE_PLANNING, return_value=True) as remove:
            planning = self._create_planning()
            slot = planning.df_planning_slot_id
            planning.unlink()
        self.assertFalse(planning.exists())
        self.assertFalse(slot.exists())
        self.assertEqual(remove.call_count, 1)

    def test_skip_context_leaves_counterpart_alone(self):
        with patch(REMOVE_PLANNING, return_value=True):
            planning = self._create_planning()
            slot = planning.df_planning_slot_id
            planning.with_context(gd_skip_planning_sync=True).unlink()
        self.assertTrue(slot.exists(), 'gd_skip_planning_sync must leave the shift untouched')
        slot.with_context(gd_skip_planning_sync=True).unlink()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def test_write_moves_slot(self):
        planning = self._create_planning()
        new_start = datetime(2026, 6, 2, 9, 0, 0)
        new_stop = datetime(2026, 6, 2, 17, 0, 0)
        planning.write({'start_datetime': new_start, 'end_datetime': new_stop})
        self.assertEqual(planning.df_planning_slot_id.start_datetime, new_start)
        self.assertEqual(planning.df_planning_slot_id.end_datetime, new_stop)

    # ------------------------------------------------------------------
    # Slot values
    # ------------------------------------------------------------------

    def test_slot_vals_only_known_fields(self):
        planning = self._create_planning()
        slot_fields = self.Slot._fields
        for key in planning._gd_slot_vals():
            self.assertIn(key, slot_fields,
                          '_gd_slot_vals() must only return fields planning.slot actually has')

    def test_slot_vals_falls_back_to_user_employee(self):
        user = self.env['res.users'].create({
            'name': 'GD Sync User',
            'login': 'gd_sync_user',
        })
        self.employee.user_id = user.id
        planning = self._create_planning(employee_id=False, user_id=user.id,
                                         id_geodynamics='gd-planning-2')
        self.assertEqual(planning._gd_slot_vals().get('resource_id'), self.employee.resource_id.id)
