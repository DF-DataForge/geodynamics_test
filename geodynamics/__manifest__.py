# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
{
    'name': "Geodynamics",

    'summary': "Geodynamics - Odoo connection by Data Forge",

    'description': """
Geodynamics module integrates Odoo with the IntelliTracer API for GPS tracking,
fleet management, employee planning, time registration, and construction site
check-in (Checkinatwork / CIAW).

Last build date: 2026-08-31 12:00:00
    """,

    'author': "Data Forge",
    'website': "https://www.data-forge.be",

    'category': 'Services/Field Service',
    'version': '19.0.0.0.4',

    # any module necessary for this one to work correctly
    'depends': ['base', 'hr', 'project', 'industry_fsm', 'account', 'hr_timesheet', 'web_gantt', 'fleet', 'hr_holidays'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
        'views/gd_planning.xml',
        'views/hr.xml',
        'views/users.xml',
        'views/partner.xml',
        'views/project.xml',
        'views/task.xml',
        'views/res_config_settings_views.xml',
        'views/employee_timesheet_group_views.xml',
        'views/timesheets_analysis_report_views.xml',
        'views/account_analytic_line_views.xml',
        'views/df_geodynamics_clocking_views.xml',
        'views/df_geodynamics_clocking_error_views.xml',
        'views/geodynamics_synch_wizard_views.xml',
        'views/df_geodynamics_vehicle_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/df_geodynamics_tracking_views.xml',
        'views/df_geodynamics_checkin_views.xml',
        'views/df_geodynamics_api_log_views.xml',
        'views/hr_leave_type_views.xml',
        'views/df_geodynamics_dashboard_views.xml',
        'views/df_geodynamics_import_wizard_views.xml',
        'views/df_geodynamics_tracking_wizard_views.xml',
        'views/df_geodynamics_checkin_wizard_views.xml',
        'views/df_geodynamics_plan_overlap_wizard_views.xml',
        'views/df_geodynamics_event_type_views.xml',
        'data/df_geodynamics_event_type_data.xml',
        'data/ir_cron_geodynamics.xml',
    ],

    'license': 'OPL-1',
}
