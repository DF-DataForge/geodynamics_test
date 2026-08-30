# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ProjectTaskType(models.Model):
    _inherit = 'project.task.type'

    # Field to mark this stage as completion stage
    df_is_completion_stage = fields.Boolean(
        string='Is Completion Stage',
        default=False,
        help='Check this if this stage represents task completion. POI will be deleted when task moves to this stage.'
    )
