# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    # Backward-compat: old camelCase field names from v17 stale views
    df_startTime = fields.Datetime(related='df_start_time', string='Start Time (compat)')
    df_endTime = fields.Datetime(related='df_end_time', string='End Time (compat)')

    # Timesheet type
    df_timesheet_type = fields.Selection(
        selection=[
            ('work', 'Werkuren'),
            ('drive', 'Onderweg'),
            ('drive_work', 'Werkverplaatsing'),
            ('break', 'In pauze'),
        ],
        string='Entry Type',
        default='work',
        help=(
            "Type van de tijdsregistratie:\n"
            "- Werkuren: gepresteerde arbeid.\n"
            "- Onderweg: reistijd die niet als werkuren worden beschouwd.\n"
            "- Werkverplaatsing: gereden kilometers / verplaatsing die "
            "worden geregistreerd als reistijd maar worden uitbetaald "
            "als normale werkuren.\n"
            "- In pauze: niet-gewerkte tijd, wordt niet uitbetaald."
        ),
    )

    # One2many to geodynamics clockings linked to this timesheet line
    df_geodynamics_clocking_ids = fields.One2many(
        'geodynamics.clocking',
        'timesheet_line_id',
        string='Geodynamics Clockings',
        help='Clockings from Geodynamics linked to this timesheet entry'
    )

    # Computed cost fields from linked clockings
    df_gd_purchase_cost = fields.Monetary(
        string='GD Purchase Cost',
        compute='_compute_gd_costs',
        store=True,
        currency_field='currency_id',
        help='Total purchase cost from linked Geodynamics clockings'
    )
    df_gd_employer_cost = fields.Monetary(
        string='GD Employer Cost',
        compute='_compute_gd_costs',
        store=True,
        currency_field='currency_id',
        help='Total employer cost from linked Geodynamics clockings'
    )
    df_gd_backoffice_cost = fields.Monetary(
        string='GD Backoffice Cost',
        compute='_compute_gd_costs',
        store=True,
        currency_field='currency_id',
        help='Total backoffice cost from linked Geodynamics clockings'
    )
    df_gd_total_cost = fields.Monetary(
        string='GD Total Cost',
        compute='_compute_gd_costs',
        store=True,
        currency_field='currency_id',
        help='Total cost from linked Geodynamics clockings'
    )
    df_gd_sales_price = fields.Monetary(
        string='GD Sales Price',
        compute='_compute_gd_costs',
        store=True,
        currency_field='currency_id',
        help='Total sales price from linked Geodynamics clockings'
    )
    df_gd_margin = fields.Monetary(
        string='GD Margin',
        compute='_compute_gd_costs',
        store=True,
        currency_field='currency_id',
        help='Total margin from linked Geodynamics clockings'
    )
    df_gd_margin_percentage = fields.Float(
        string='GD Margin %',
        compute='_compute_gd_costs',
        store=True,
        help='Margin percentage from linked Geodynamics clockings'
    )

    # Count of linked clockings
    df_gd_clocking_count = fields.Integer(
        string='Clocking Count',
        compute='_compute_df_gd_clocking_count',
        help='Number of Geodynamics clockings linked to this timesheet'
    )

    @api.depends('df_geodynamics_clocking_ids')
    def _compute_gd_costs(self):
        """Compute total costs from all linked Geodynamics clockings"""
        for line in self:
            # Note: Cost fields don't exist yet in geodynamics.clocking model
            # Set all to 0 for now
            line.df_gd_purchase_cost = 0.0
            line.df_gd_employer_cost = 0.0
            line.df_gd_backoffice_cost = 0.0
            line.df_gd_total_cost = 0.0
            line.df_gd_sales_price = 0.0
            line.df_gd_margin = 0.0
            line.df_gd_margin_percentage = 0.0

    @api.depends('df_geodynamics_clocking_ids')
    def _compute_df_gd_clocking_count(self):
        """Count linked clockings"""
        for line in self:
            line.df_gd_clocking_count = len(line.df_geodynamics_clocking_ids)

    def action_view_geodynamics_clockings(self):
        """Open linked Geodynamics clockings"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Geodynamics Clockings',
            'res_model': 'geodynamics.clocking',
            'view_mode': 'list,form',
            'domain': [('timesheet_line_id', '=', self.id)],
            'context': {'default_timesheet_line_id': self.id},
        }

