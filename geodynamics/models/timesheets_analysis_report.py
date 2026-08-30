# -*- coding: utf-8 -*-
from odoo import models,fields,api


class TimesheetsAnalysisReport(models.Model):
    _inherit = "timesheets.analysis.report"

    df_start_time = fields.Datetime(string='Starttijd')
    df_end_time = fields.Datetime(string='Eindtijd')

    @api.model
    def _select(self):
        return super()._select() + """,
            A.df_start_time AS df_start_time,
            A.df_end_time AS df_end_time
        """

    # df_startTime = fields.Datetime(string='Starttijd')
    # df_endTime = fields.Datetime(string='Eindtijd')
    #
    # @api.model
    # def _select(self):
    #     return super(self)._select() + """,
    #         A.df_startTime AS df_startTime,
    #         A.df_endTime AS df_endTime
    #     """

    def action_open_analytic_line(self):
        """Open the underlying account.analytic.line in form view.
        Since the SQL view uses A.id as id, self.id is the analytic line id.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name or "Timesheet",
            "res_model": "account.analytic.line",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

