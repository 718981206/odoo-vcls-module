# -*- coding: utf-8 -*-
{
    'name': "vcls-project",

    'summary': """
        VCLS customs project module.""",

    'description': """
    """,

    'author': "VCLS",
    'website': "http://www.voisinconsulting.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/12.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.9',

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'project',
        'vcls-crm',
        'vcls-hr',
        'project_forecast',
        'sale_project_timesheet_by_seniority',
        'project_task_stage_allow_timesheet',
        'project_task_default_stage',
        'project_parent_task_filter',
        'sale_quote_project_forecast',
        ],

    # always loaded
    'data': [

        ### SECURITY ###
        'security/vcls_groups.xml',
        'security/ir.model.access.csv',

        ### VIEWS ###
        'views/task_type_views.xml',
        'views/dev_project_views.xml',
        'views/dev_task_views.xml',
        'views/task_views.xml',
        'views/employee_views.xml',
        'views/product_views.xml',
        'views/sale_order_views.xml',

        ### MENUS ###
        'views/dev_project_menu.xml',
        'views/program_views_menu.xml',
        'views/project_views.xml',
        'views/project_forecast_views.xml',
    ],

    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}