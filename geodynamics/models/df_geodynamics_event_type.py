# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api


class GeodynamicsEventType(models.Model):
    _name = 'df.geodynamics.event.type'
    _description = 'Geodynamics Event Type'
    _order = 'df_code'

    name = fields.Char(string='Name', required=True)
    df_code = fields.Char(string='Code', required=True, index=True)
    df_log_timesheets = fields.Boolean(
        string='Log hours as cost',
        default=True,
        help='Events of this type are always imported as timesheet lines ("urenstaten") on the task. '
             'When this box is ticked their hours are also charged to the project: Odoo keeps the cost '
             'it derives from the employee hourly cost. When it is unticked the timesheet line is still '
             'created, but with a zero cost, so the hours do not show up in the project costs.',
    )

    _sql_constraints = [
        ('code_uniq', 'UNIQUE(df_code)', 'Event type code must be unique.'),
    ]

    @api.model
    def _code_map(self):
        """Return {df_code: record} for every event type.

        The table holds one record per Geodynamics event type (10 rows), so the
        callers of the post-calculation import can look up the event type of each
        event without a query per event.
        """
        return {rec.df_code: rec for rec in self.sudo().search([])}
