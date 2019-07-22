# -*- coding: utf-8 -*-
{
    'name': "vcls-suppliers",

    'summary': """
        External Resource Management""",

    'description': """
        External Resource Management
    """,

    'author': "VCLS",
    'website': "https://voisinconsulting.com/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/12.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.5',

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'survey',
        'vcls-contact',
        'vcls-hr',
        'vcls-project',
        'sale_purchase',
        ],

    # always loaded
    'data': [
        ### RECORDS
        'data/expertise.area.csv',
        'data/project.supplier.type.csv',
        'data/hr_data.xml',

        ### SECURITY
        'security/vcls_groups.xml',
        'security/ir.model.access.csv',

        ### VIEWS
        'views/sup_contact_views.xml',
        'views/sup_employee_views.xml',
        'views/purchase_views.xml',
        'views/project_portal_templates.xml',


        ### MENUS
        'views/supplier_menu.xml',  
        
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
