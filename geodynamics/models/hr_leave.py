# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, api


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    @api.depends('date_from', 'date_to', 'resource_calendar_id', 'holiday_status_id.request_unit')
    def _compute_duration(self):
        super()._compute_duration()
        for leave in self:
            if leave.number_of_days <= 0 and leave.date_from and leave.date_to:
                days = max(1.0, (leave.date_to.date() - leave.date_from.date()).days + 1)
                leave.number_of_days = days
                leave.number_of_hours = days * 8.0
