# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields


class PlanningSlot(models.Model):
    """Odoo Planning shift, kept in sync with its Geodynamics planning."""

    _inherit = 'planning.slot'

    df_gd_planning_ids = fields.One2many(
        comodel_name='df.geodynamics.planning', inverse_name='df_planning_slot_id',
        string='Geodynamics plannings', copy=False,
        help='Geodynamics plannings kept in sync with this shift. Deleting the shift '
             'also deletes them, which removes them from Geodynamics as well.')

    def unlink(self):
        """Delete the Geodynamics counterpart along with the shift.

        'gd_skip_planning_sync' means the plannings are already being deleted and
        are taking their shifts with them, so there is nothing to mirror back.
        """
        if not self.env.context.get('gd_skip_planning_sync'):
            # sudo: whoever cleans up a shift in the Planning app is not necessarily
            # allowed to touch Geodynamics plannings.
            gd_plannings = self.env['df.geodynamics.planning'].sudo().search(
                [('df_planning_slot_id', 'in', self.ids)])
            if gd_plannings:
                # Warn first: once the records are gone their names cannot be read.
                gd_plannings._gd_notify_counterpart('gd_deleted')
                # This also removes them from Geodynamics itself
                # (df.geodynamics.planning.unlink() calls the API).
                gd_plannings.with_context(gd_skip_planning_sync=True).unlink()
        return super().unlink()
