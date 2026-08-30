from odoo import models, fields, api, _


class GeodynamicsTracking(models.Model):
    _name = 'df.geodynamics.tracking'
    _description = 'Geodynamics Location Tracking'
    _order = 'df_timestamp desc'

    df_employee_id = fields.Many2one('hr.employee', string='Employee', index=True, ondelete='cascade')
    df_vehicle_id = fields.Many2one('df.geodynamics.vehicle', string='Vehicle', index=True, ondelete='set null')
    df_timestamp = fields.Datetime(string='Timestamp', index=True, required=True)
    df_latitude = fields.Float(string='Latitude', digits=(10, 7))
    df_longitude = fields.Float(string='Longitude', digits=(10, 7))
    df_speed = fields.Float(string='Speed (km/h)')
    df_address = fields.Char(string='Address')
    df_status = fields.Selection([
        ('driving', 'Driving'),
        ('idle', 'Idle'),
        ('stopped', 'Stopped'),
        ('offline', 'Offline'),
    ], string='Status')
    df_distance_km = fields.Float(string='Distance (km)')
    df_raw_payload = fields.Json(string='Raw Data')
    df_date = fields.Date(string='Date', index=True, compute='_compute_date', store=True)

    @api.depends('df_timestamp')
    def _compute_date(self):
        for rec in self:
            rec.df_date = rec.df_timestamp.date() if rec.df_timestamp else False
