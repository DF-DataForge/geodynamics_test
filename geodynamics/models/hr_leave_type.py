# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    df_geodynamics_id = fields.Char(
        string='Geodynamics ID',
        help='The ID of this absence type in Geodynamics. Set automatically when exporting.',
        index=True,
    )
    df_geodynamics_name = fields.Char(
        string='Geodynamics',
        help='Name of the matching absence type in Geodynamics. This is the link '
             'used to sync leaves between Geodynamics and Odoo. Leave types without '
             'this value set are left outside the leave sync.',
    )
