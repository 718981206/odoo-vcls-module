#Odoo Imports
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

class Employee(models.Model):
    
    _inherit = 'hr.employee'

    """#we add the default rate product
    rate_id = fields.Many2one(
        comodel_name = 'product.template',
        string = 'Default Rate',
        domain = "[('seniority_level_id','!=',False)]",
    )"""

    default_rate_ids = fields.Many2many(
        'product.template',
        string = 'Default Rates',
        domain = "[('seniority_level_id','!=',False)]",
    )

    seniority_level_id = fields.Many2one(
        comodel_name = 'hr.employee.seniority.level',
        compute = '_compute_default_seniority',
        string = 'Default Seniority',
    )

    @api.depends('default_rate_ids')
    def _compute_default_seniority(self):
        for emp in self:
            if emp.default_rate_ids:
                emp.seniority_level_id = emp.default_rate_ids[0].seniority_level_id