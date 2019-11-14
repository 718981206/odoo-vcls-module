# -*- coding: utf-8 -*-
{
    'name': "vcls security",

    'summary': """
        VCLS groups and security.""",
    'description': """
    """,
    'author': "VCLS",
    'website': "http://www.voisinconsulting.com",
    'version': '0.0.1',
    'depends': [
        'base',
        'project',
        'sale',
        'purchase',
        'hr_timesheet',
        'project_forecast',
        'crm',
        'web_access_rule_buttons',
        'agreement_legal',
    ],
    'data': [
        'security/pre_hooks.sql',
        'security/vcls_groups.xml',
        'security/ir.model.access.csv',
        'security/account_manager_security/ir.model.access.csv',
        'security/account_manager_security/account_manager_security.xml',
        'security/lc_security.xml',
        'security/consultant_security.xml',
        'security/project_controller_security.xml',
        'security/cross_company_invoicing.xml',
        'views/menus.xml',
    ],
    'demo': [
    ],
}
