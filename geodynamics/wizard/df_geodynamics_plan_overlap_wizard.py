# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api


class GeodynamicsPlanOverlapWizard(models.TransientModel):
    _name = 'df.geodynamics.plan.overlap.wizard'
    _description = 'Resolve overlapping Geodynamics plannings'

    task_ids = fields.Many2many('project.task', string='Taken', readonly=True)
    overlap_planning_ids = fields.Many2many(
        'df.geodynamics.planning', string='Overlappende planningen',
        compute='_compute_overlap_planning_ids', readonly=True,
    )
    action = fields.Selection(
        selection=[
            ('keep', 'De huidige behouden'),
            ('replace', 'De huidige wissen en vervangen door de nieuwe'),
            ('cancel', 'Niet inplannen'),
        ],
        string='Wat wil je doen met overlappende planningen?',
        required=True, default='replace',
    )

    @api.depends('task_ids')
    def _compute_overlap_planning_ids(self):
        for wizard in self:
            plannings = self.env['df.geodynamics.planning']
            for task in wizard.task_ids:
                plannings |= task.df_gd_planning_overlapped_ids
            wizard.overlap_planning_ids = plannings

    def action_confirm(self):
        self.ensure_one()
        if self.action == 'cancel':
            return {'type': 'ir.actions.act_window_close'}

        for task in self.task_ids:
            if self.action == 'replace':
                # Deleting these plannings also removes them from Geodynamics
                # (df.geodynamics.planning.unlink() calls the API).
                task.df_gd_planning_overlapped_ids.unlink()
            # Plan the task, bypassing the overlap check (already resolved here).
            task.with_context(gd_ignore_overlap=True).sendPlanningToDGdWn()

        return {'type': 'ir.actions.act_window_close'}
