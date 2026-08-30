# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields


class EmployeeTimesheetGroup(models.Model):
    _name = 'employee.timesheet.group'
    _description = 'Employee Timesheet Group'

    name = fields.Char(string='Name', required=True)
    employee_ids = fields.Many2many('hr.employee', 'employee_timesheet_group_rel', 'group_id', 'employee_id', string='Employees')
    extra_time = fields.Integer(string='Extra Time (minutes)', default=0, help='Extra time in minutes to add per day')
    minimum_time = fields.Integer(string='Minimum Time (minutes)', default=0, help='Minimum time in minutes required per day, If working hours of a day greater than minimum time, extra time will be recorded')
    active = fields.Boolean(default=True)
