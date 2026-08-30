from odoo import models, fields, api

class AccAnalLine(models.Model):
    _inherit = 'account.analytic.line'

    df_start_time = fields.Datetime(string='Starttijd')
    df_end_time = fields.Datetime(string='Eindtijd')

    df_gd_type = fields.Selection(
        [('0', 'Absence'), ('1', 'Activity'), ('2', 'Allowance'), ('3', 'Break'), ('4', 'Movement'), ('5', 'Work'), ('6', 'Error'),
         ('7', 'Unpaid'), ('8', 'TravelTime'), ('9', 'External')], string='Event Geodynamics')

    df_gd_eventtype = fields.Selection([
        ('0', 'Absence paid'),
        ('1', 'Absence unpaid'),
        ('2', 'Activity'),
        ('3', 'Break'),
        ('4', 'Movement driver'),
        ('5', 'Movement passenger'),
        ('6', 'Movement single driver'),
        ('7', 'Work'),
        ('8', 'Load/Unload'),
        ('9', 'Travel time'),
        ('10', 'External'),
        ('11', 'Unpaid'),
        ('12', 'Allowance'),
        ('13', 'Error')
    ], string="Event type Geodynamics")

    df_gd_start_location = fields.Char(string='Startlocatie')
    df_gd_stop_location = fields.Char(string='Stoplocatie')
    df_gd_mileage = fields.Float(string='Kilometerstand', digits=(10, 1))
    df_gd_start_resource_id = fields.Many2one('fleet.vehicle', string='Start voertuig')
    df_gd_stop_resource_id = fields.Many2one('fleet.vehicle', string='Stop voertuig')