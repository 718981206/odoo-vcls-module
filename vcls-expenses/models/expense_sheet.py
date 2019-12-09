# -*- coding: utf-8 -*-

from odoo import models, fields, api

import logging
_logger = logging.getLogger(__name__)

class ExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'


    #################
    # CUSTOM FIELDS #
    #################

    type = fields.Selection([
        ('project', 'Project'),
        ('admin', 'Admin'),
        ('mobility', 'Mobility'),
    ], 
    required = True, string = 'Type')

    #we link parent projects only
    project_id = fields.Many2one(
        'project.project', 
        string = 'Related Project',
        domain="[('parent_id','=',False)]",
    )

    analytic_account_id = fields.Many2one(
        'account.analytic.account', 
        string = 'Analytic Account',
    )

    sale_order_id = fields.Many2one(
        'sale.order', 
        string = 'Related Sale Order',
    )

    company_id = fields.Many2one(
        related = 'employee_id.company_id'
    )

    ######################
    # OVERWRITTEN FIELDS #
    ######################
    user_id = fields.Many2one(
        'res.users', 
        'Approver', 
        readonly=True, 
        copy=False, 
        states={'draft': [('readonly', False)]}, 
        track_visibility='onchange', 
        oldname='responsible_id',
        compute = '_compute_user_id'
    )

    @api.multi
    def approve_expense_sheets(self):
        if not self.user_has_groups('hr_expense.group_hr_expense_user'):
            raise UserError(_("Only Managers and HR Officers can approve expenses"))
        elif not self.user_has_groups('hr_expense.group_hr_expense_manager'):
            #current_managers = self.employee_id.parent_id.user_id | self.employee_id.department_id.manager_id.user_id | self.employee_id.expense_manager_id

            if self.employee_id.user_id == self.env.user:
                raise UserError(_("You cannot approve your own expenses"))

            #if not self.env.user in current_managers:
                #raise UserError(_("You can only approve your department expenses"))

        responsible_id = self.user_id.id or self.env.user.id
        self.write({'state': 'approve', 'user_id': responsible_id})
        self.activity_update()

    ###################
    # COMPUTE METHODS #
    ###################

    @api.depends('type', 'project_id', 'employee_id')
    def _compute_user_id(self):
        for record in self:
            
            if record.type == 'project':
                if record.project_id:
                    record.user_id = record.project_id.user_id
                else:
                    record.user_id = False
            else:
                #line manager to be the approver
                if record.employee_id:
                    record.user_id = record.employee_id.parent_id.user_id
                else:
                    record.user_id = False
    
    @api.onchange('type')
    def change_type(self):
        for sheet in self:
            sheet.project_id=False

    @api.onchange('project_id')
    def change_project(self):
        for rec in self:
            _logger.info("EXPENSE PROJECT {}".format(rec.type))
            if rec.project_id:
                #grab analytic account from the project
                if rec.type == 'admin':
                    rec.analytic_account_id = rec.project_id.analytic_account_id
                    rec.sale_order_id = False

                #we look for the SO in case of project (to be able to re-invoice)
                elif rec.type == 'project':
                    so = self.env['sale.order'].search([('project_id','=',rec.project_id.id)],limit=1)
                    if so:
                        rec.sale_order_id = so.id
                    else:
                        rec.sale_order_id = False
                    rec.analytic_account_id = False

                else:
                    rec.sale_order_id = False
                    rec.analytic_account_id = False          

    @api.multi
    def open_pop_up_add_expense(self):
        for rec in self:
            action = self.env.ref('vcls-expenses.action_pop_up_add_expense').read()[0]
            if rec.type == 'admin':
                action['context'] = {'default_employee_id': rec.employee_id.id,
                                    'default_analytic_account_id': rec.analytic_account_id.id,
                                    'default_sheet_id': rec.id}
            elif rec.type == 'project':
                action['context'] = {'default_employee_id': rec.employee_id.id,
                                    'default_sale_order_id': rec.sale_order_id.id,
                                    'default_sheet_id': rec.id}
            return action


class HrExpense(models.Model):

    _inherit = "hr.expense"

    is_product_employee = fields.Boolean(related='product_id.is_product_employee', readonly=True)

    @api.model
    def _setup_fields(self):
        super(HrExpense, self)._setup_fields()
        self._fields['unit_amount'].states = None
        self._fields['unit_amount'].readonly = False
        self._fields['product_uom_id'].readonly = True

    @api.multi
    def action_get_attachment_view(self):
        self.ensure_one()
        res = self.env['ir.actions.act_window'].for_xml_id('vcls-expenses', 'action_attachment_expense')
        res['domain'] = [('res_model', '=', 'hr.expense'), ('res_id', 'in', self.ids)]
        res['context'] = {'default_res_model': 'hr.expense', 'default_res_id': self.id}
        res['view_mode'] = 'form'
        res['view_id'] = self.env.ref('vcls-expenses.view_hr_expense_attachment')
        res['target'] = 'new'
        return res