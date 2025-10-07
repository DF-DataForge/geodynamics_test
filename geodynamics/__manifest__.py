# -*- coding: utf-8 -*-
{
    'name': "Geodynamics",

    'summary': "Geodynamics - Odoo connection by Data Forge",

    'description': """
Long description of module's purpose
    """,

    'author': "Data Forge",
    'website': "https://www.data-forge.be",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'hr', 'project', 'industry_fsm', 'account'],

    # always loaded
    'data': [
        #'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
        'views/gd_planning.xml',
        'views/hr.xml',
        'views/users.xml',
        'views/partner.xml',
        'views/project.xml',
        'views/task.xml',
        'views/res_config_settings_views.xml',
        'security/ir.model.access.csv'
    ]
}

