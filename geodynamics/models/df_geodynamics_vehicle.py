# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api, _


class GeodynamicsVehicle(models.Model):
    _name = 'df.geodynamics.vehicle'
    _description = 'Geodynamics Vehicle'
    _order = 'df_name'
    _rec_name = 'df_name'

    df_name = fields.Char(string='Name', required=True)
    df_code = fields.Char(string='Vehicle Code', index=True)
    df_license_plate = fields.Char(string='License Plate')
    df_brand = fields.Char(string='Brand')
    df_model_name = fields.Char(string='Model')
    df_vehicle_type = fields.Char(string='Vehicle Type')
    df_geodynamics_id = fields.Char(string='Geodynamics ID', index=True)
    active = fields.Boolean(default=True)
    df_raw_payload = fields.Json(string='Raw Data')
    df_last_sync_date = fields.Datetime(string='Last Synced')

    _sql_constraints = [
        ('geodynamics_vehicle_code_uniq', 'UNIQUE(df_code)', 'Vehicle code must be unique.'),
    ]

    def action_gd_export_vehicles(self):
        """Export selected vehicles to Geodynamics (callable from list view button)."""
        wizard = self.env['df.geodynamics.import.wizard'].create({
            'df_import_type': 'fleet',
            'df_direction': 'export',
        })
        return wizard._export_fleet(vehicle_ids=self)
