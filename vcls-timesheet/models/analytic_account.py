# -*- coding: utf-8 -*-

from odoo import models, fields, tools, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
from datetime import timedelta
from odoo.osv import expression

import logging
import datetime
import math
_logger = logging.getLogger(__name__)


class AnalyticLine(models.Model):

    _inherit = 'account.analytic.line'

    stage_id = fields.Selection([
        # ('forecast', 'Stock'),
        ('draft', '0. Draft'), 
        ('lc_review', '1. LC review'), 
        ('pc_review', '2. PC review'), 
        ('carry_forward', 'Carry Forward'),
        ('adjustment_validation', '4. Adjustment Validation'),
        ('invoiceable', '5. Invoiceable'),
        ('invoiced', '6. Invoiced'),
        ('historical','7. Historical'),
        ('outofscope', 'Out Of Scope'),
        ], default='draft')

    lc_comment = fields.Char(string="Comment")

    deliverable_id = fields.Many2one(
        'product.deliverable',
        string='Deliverable',
        related='task_id.sale_line_id.product_id.deliverable_id',
        store=True,
    )

    # Used in order to group by client
    partner_id = fields.Many2one(
        'res.partner',
        string='Client',
        related='project_id.partner_id',
        store=True,
    )

    adjustment_reason_id = fields.Many2one('timesheet.adjustment.reason', string="Adjustment Reason")

    time_category_id = fields.Many2one(
        comodel_name='project.time_category',
        string="Time Category",
    )

    # Rename description label
    name = fields.Char('External Comment', required=True)

    internal_comment = fields.Char(string='')

    at_risk = fields.Boolean(string='Timesheet at risk', readonly=True)

    # OVERWRITE IN ORDER TO UPDATE LABEL
    unit_amount_rounded = fields.Float(
        string="Revised Time",
        default=0.0,
        copy=False,
    )
    
    required_lc_comment = fields.Boolean(compute='get_required_lc_comment')

    rate_id = fields.Many2one(
        comodel_name='product.product',
        default = False,
        readonly = True,
    )

    so_line_unit_price = fields.Monetary(
        'Sales Oder Line Unit Price',
        readonly=True,
        store=True,
        default=0.0,
    )

    so_line_currency_id = fields.Many2one(
        'res.currency',
        related='so_line.currency_id',
        store=True,
        string='Sales Order Currency',
    )
    adj_reason_required = fields.Boolean()
    main_project_id = fields.Many2one(
        'project.project', string='Main Project',
        domain=[('parent_id', '=', False)],
    )

    billability = fields.Selection([
        ('na', 'N/A'),
        ('billable', 'BILLABLE'),
        ('non_billable', 'NON BILLABLE'),],
        compute = '_compute_billability',
        store = True,
        default = 'na',
        )

    @api.depends('project_id')
    def _compute_billability(self):
        timesheets = self.filtered(lambda t: t.is_timesheet and t.project_id)
        for ts in timesheets:
            if ts.project_id.project_type == 'client':
                ts.billability = 'billable'
            else:
                ts.billability = 'non_billable'


    @api.model
    def show_grid_cell(self, domain=[], column_value='', row_values={}):
        line = self.sudo().search(domain, limit=1)
        date = column_value
        if not line:
            # fetch the latest line
            task_value = row_values.get('task_id')
            task_id = task_value and task_value[0] or False
            if task_id:
                direct_previous_line = self.sudo().search([
                    ('date', '<', date),
                    ('task_id', '=', task_id),
                ], limit=1, order='date desc')
                if direct_previous_line:
                    task_id = direct_previous_line.task_id
                    main_project_id = task_id.project_id
                    main_project_id = main_project_id or main_project_id.parent_id
                    values = {
                        'unit_amount': 0,
                        'date': date,
                        'project_id': direct_previous_line.project_id.id,
                        'task_id': task_id.id,
                        'main_project_id': main_project_id.id,
                        'name': direct_previous_line.name,
                        'time_category_id': direct_previous_line.time_category_id.id,
                    }
                    line = self.create(values)

        form_view_id = self.env.ref('timesheet_grid.timesheet_view_form').id
        return {
            'name': _('Timesheet'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': self._name,
            'res_id': line.id,
            'view_id': form_view_id,
            'views': [(form_view_id, 'form')],
            'target': 'new',
            'context': {},
        }

    @api.multi
    def adjust_grid(self, row_domain, column_field, column_value, cell_field, change):
        """
        We override this to avoit the default naming 'Timesheet Adjustment' when using the grid view
        """
        if column_field != 'date' or cell_field != 'unit_amount':
            raise ValueError(
                "{} can only adjust unit_amount (got {}) by date (got {})".format(
                    self._name,
                    cell_field,
                    column_field,
                ))

        additionnal_domain = self._get_adjust_grid_domain(column_value)
        domain = expression.AND([row_domain, additionnal_domain])
        line = self.search(domain)

        day = column_value.split('/')[0]
        if len(line) > 1:  # copy the last line as adjustment
            line[0].copy({
                #'name': _('Timesheet Adjustment'),
                column_field: day,
                cell_field: change
            })
        elif len(line) == 1:  # update existing line
            line.write({
                cell_field: line[cell_field] + change
            })
        else:  # create new one
            self.search(row_domain, limit=1).copy({
                #'name': _('Timesheet Adjustment'),
                column_field: day,
                cell_field: change
            })
        return False

    @api.model
    def _get_at_risk_values(self, project_id, employee_id):
        project = self.env['project.project'].browse(project_id)
        if project.sale_order_id.state not in ['sale', 'done']:
            return True
        employee_id = self.env['hr.employee'].browse(employee_id)

        core_team = project.core_team_id
        if employee_id and core_team:
            project_employee = core_team.consultant_ids | \
                           core_team.ta_ids | \
                           core_team.lead_backup | \
                           core_team.lead_consultant
            if employee_id[0] not in project_employee:
                return True
        return False

    @api.model
    def create(self, vals):
        if vals.get('employee_id', False) and vals.get('project_id', False):
            # rounding to 15 mins
            if vals['unit_amount'] % 0.25 != 0:
                old = vals.get('unit_amount', 0)
                vals['unit_amount'] = math.ceil(old * 4) / 4

            # check if this is a timesheet at risk
            vals['at_risk'] = self.sudo()._get_at_risk_values(vals.get('project_id'),
                                                       vals.get('employee_id'))

        if vals.get('time_category_id') == self.env.ref('vcls-timesheet.travel_time_category').id:
            task = self.env['project.task'].browse(vals['task_id'])
            if task.sale_line_id:
                unit_amount_rounded = vals['unit_amount'] * task.sale_line_id.order_id.travel_invoicing_ratio
                vals.update({'unit_amount_rounded': unit_amount_rounded})
                
        if not vals.get('main_project_id') and vals.get('project_id'):
            project_id = self.env['project.project'].browse(vals['project_id'])
            main_project_id = project_id.parent_id or project_id
            vals['main_project_id'] = main_project_id.id

        return super(AnalyticLine, self).create(vals)

    @api.multi
    def write(self, vals):
        # we automatically update the stage if the ts is validated and stage = draft
        so_update = False
        orders = self.env['sale.order']
        #_logger.info("ANALYTIC WRITE {}".format(vals))

        # we loop the lines to manage specific usecases
        for line in self:

            # Timesheet cases
            if line.is_timesheet and line.project_id and line.employee_id:


                if vals.get('unit_amount', False):
                    #the coded amount is changed
                    if vals['unit_amount'] % 0.25 != 0:
                        old = vals.get('unit_amount', 0)
                        vals['unit_amount'] = math.ceil(old * 4) / 4
                    
                    #we preserve a potential modification of the rounded_value in the past
                    delta = vals['unit_amount'] - line.unit_amount
                    vals['unit_amount_rounded'] = vals.get('unit_amount_rounded', line.unit_amount_rounded)+delta

                # automatically set the stage to lc_review according to the conditions
                if vals.get('validated', line.validated):
                    if vals.get('stage_id', line.stage_id) == 'draft':
                        vals['stage_id'] = 'lc_review'

                # review of the lc needs sudo() to write on validated ts
                if line.stage_id == 'lc_review':
                    project = self.env['project.project'].browse(
                        vals.get('project_id', line.project_id.id))
                    if project.user_id.id == self._uid:  # if the user is the lead consultant, we autorize the modification
                        self = self.sudo()

                # if one of the 3 important value has changed, and the stage changes the delivered amount
                if (vals.get('date', False) or vals.get('unit_amount_rounded',False) or vals.get('stage_id', False)) and (vals.get('stage_id', line.stage_id) in ['invoiced','invoiceable','historical']):
                    _logger.info("Order timesheet update for {}".format(line.name))
                    so_update = True
                    orders |= line.so_line.order_id

                # if the sale order line price as not been captured yet
                if vals.get('so_line',
                            line.so_line.id) and line.so_line_unit_price == 0.0:
                    task = self.env['project.task'].browse(
                        vals.get('task_id', line.task_id.id))
                    so_line = self.env['sale.order.line'].browse(
                        vals.get('so_line', line.so_line.id))

                    if task.sale_line_id != so_line:  # if we map to a rate based product
                        vals['so_line_unit_price'] = so_line.price_unit
                        vals['rate_id'] = so_line.product_id.id
                        so_update = True
                        orders |= line.so_line.order_id

            if (vals.get('time_category_id') == self.env.ref('vcls-timesheet.travel_time_category').id or
                (vals.get('unit_amount') and line.time_category_id.id == self.env.ref('vcls-timesheet.travel_time_category').id)) and\
                    line.task_id.sale_line_id:
                unit_amount = vals.get('unit_amount') or line.unit_amount
                vals.update({
                    'unit_amount_rounded': unit_amount * line.task_id.sale_line_id.order_id.travel_invoicing_ratio
                            })
        if vals.get('timesheet_invoice_id'):
            vals['stage_id'] = 'invoiced'
        ok = super(AnalyticLine, self).write(vals)

        if ok and so_update:
            orders._compute_timesheet_ids()
            # force recompute
            for order in orders:
                order.timesheet_limit_date = order.timesheet_limit_date

        return ok

    @api.multi
    def finalize_lc_review(self):
        self._finalize_lc_review()

    @api.multi
    def _finalize_lc_review(self):
        context = self.env.context
        timesheet_ids = context.get('active_ids',[])
        timesheets = self.env['account.analytic.line'].browse(timesheet_ids)
        if len(timesheets) == 0:
            raise ValidationError(_("Please select at least one record!"))

        timesheets_in = timesheets.filtered(lambda r: r.stage_id=='lc_review' and (r.project_id.user_id.id == r.env.user.id or r.env.user.has_group('vcls-hr.vcls_group_superuser_lvl2')))
        timesheets_out = (timesheets - timesheets_in) if timesheets_in else timesheets
        #_logger.info("names {} stage {} user {} out {}".format(timesheets.mapped('name'),timesheets.mapped('stage_id'),timesheets_out.mapped('name')))
        for timesheet in timesheets_in:
                timesheet.sudo().write({'stage_id':'pc_review'})
        if len(timesheets_out) > 0:
            message = "You don't have the permission for the following timesheet(s) :\n"
            for timesheet in timesheets_out:
                message += " - " + timesheet.name + "\n"
            raise ValidationError(_(message))

    @api.multi
    def finalize_pc_review(self):
        self._pc_change_state('invoiceable')

    @api.multi
    def _pc_change_state(self,new_stage='invoiceable'):
        """
            THis method covers all the use cases of the project controller, modifying timesheet stages.
            Server actions and buttons are calling this method.
        """
        context = self.env.context
        timesheet_ids = context.get('active_ids',[])
        timesheets = self.env['account.analytic.line'].browse(timesheet_ids)
        if len(timesheets) == 0:
            raise ValidationError(_("Please select at least one record!"))

        user_authorized = (self.env.user.has_group('vcls-hr.vcls_group_superuser_lvl2') or self.env.user.has_group('vcls_security.group_project_controller'))
        if not user_authorized:
            raise ValidationError(_("You need to be part of the 'Project Controller' group to perform this operation. Thank you."))

        #_logger.info("NEW TS STAGE:{}".format(new_stage))

        if new_stage=='invoiceable':
            timesheets_in = timesheets.filtered(lambda r: (r.stage_id=='pc_review' or r.stage_id=='carry_forward'))

            #adj_validation_timesheets = timesheets_in.filtered(lambda r: r.required_lc_comment == True)
            #invoiceable_timesheets = (timesheets_in - adj_validation_timesheets) if adj_validation_timesheets else timesheets_in

            #adj_validation_timesheets.write({'stage_id': 'adjustment_validation'})
            #invoiceable_timesheets.write({'stage_id': 'invoiceable'})
            timesheets_in.write({'stage_id': 'invoiceable'})

        elif new_stage=='outofscope':
            timesheets_in = timesheets.filtered(lambda r: (r.stage_id=='pc_review' or r.stage_id=='carry_forward'))
            _logger.info("NEW TS STAGE outofscope:{}".format(timesheets_in.mapped('name')))
            timesheets_in.write({'stage_id': 'outofscope'})

        elif new_stage=='carry_forward':
            timesheets_in = timesheets.filtered(lambda r: (r.stage_id=='pc_review'))
            _logger.info("NEW TS STAGE carry_forward:{}".format(timesheets_in.mapped('name')))
            timesheets_in.write({'stage_id': 'carry_forward'})

        else:
            timesheets_in = False

        timesheets_out = (timesheets - timesheets_in) if timesheets_in else timesheets
        if len(timesheets_out) > 0:
            message = "Following timesheet(s) are not in the proper stage to perform the required action:\n"
            for timesheet in timesheets_out:
                message += " - " + timesheet.name + "\n"
            raise ValidationError(_(message))

    @api.multi
    def _finalize_pc_review(self):
        self._pc_change_state('invoiceable')

    @api.multi
    def set_outofscope(self):
        self._pc_change_state('outofscope')

    @api.multi
    def set_carry_forward(self):
        self._pc_change_state('carry_forward')

    @api.depends('user_id')
    def _compute_employee_id(self):
        for record in self:
            if record.user_id:
                resource = self.env['resource.resource'].search([('user_id','=',record.user_id.id)])
                employee = self.env['hr.employee'].search([('resource_id','=',resource.id)])
                record.employee_id = employee

    @api.onchange('unit_amount_rounded', 'unit_amount')
    def get_required_lc_comment(self):
        for rec in self:
            #we round to quarter to avoir the minute entry
            if rec.unit_amount % 0.25 != 0:
                rec.unit_amount = math.ceil(rec.unit_amount * 4) / 4
            else:
                pass
            if rec.unit_amount_rounded % 0.25 != 0:
                rec.unit_amount_rounded = math.ceil(rec.unit_amount_rounded * 4) / 4
            else:
                pass
                 
            #if the values aren't the same, then we force the lc_comment.
            if float_compare(rec.unit_amount_rounded, rec.unit_amount, precision_digits=2) == 0:
                rec.required_lc_comment = False
            else:
                rec.required_lc_comment = True

    @api.onchange('unit_amount_rounded')
    def onchange_adj_reason_readonly(self):
        adj_reason_required = False
        if self.unit_amount != self.unit_amount_rounded:
            adj_reason_required = True
        self.adj_reason_required = adj_reason_required

    @api.onchange('main_project_id')
    def onchange_task_id_project_related(self):
        #we clear the existing task_id and project_id if not logged from task
        if not self._context.get('log_from_task',False):
            self.task_id = False
            self.project_id = False
        #we return the proper domain
        if self.main_project_id:
            projects = self.main_project_id | self.main_project_id.child_id
            return {'domain': {
                'task_id': [('project_id', 'in', projects.ids), ('stage_id.allow_timesheet', '=', True)]
            }}

    @api.onchange('task_id')
    def onchange_task_id(self):
        if self._context.get('desc_order_display'):
            self.project_id = self.task_id.project_id
        if not self.main_project_id and self.task_id:
            main_project_id = self.task_id.project_id
            self.main_project_id = main_project_id.parent_id or main_project_id

    @api.multi
    def button_details_lc(self):
        view = {
            'name': _('Details'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.analytic.line',
            'view_id': self.env.ref('vcls-timesheet.vcls_timesheet_lc_view_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {
                'form_view_initial_mode': 'edit',
                'force_detailed_view': True,
                'set_fields_readonly': self.stage_id != 'lc_review'
            },
            'res_id': self.id,
        }
        return view
    
    @api.multi
    def button_details_pc(self):
        view = {
            'name': _('Details'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.analytic.line',
            'view_id': self.env.ref('vcls-timesheet.vcls_timesheet_pc_view_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {
                'form_view_initial_mode': 'edit',
                'force_detailed_view': True,
            },
            'res_id': self.id,
        }
        return view

    def lc_review_approve_timesheets(self):
        self.search([('stage_id', '=', 'lc_review')]).write({'stage_id': 'pc_review'})

    def pc_review_approve_timesheets(self):
        self.search([('stage_id', '=', 'pc_review'), ('lc_comment', '=', False)]).\
            write({'stage_id': 'invoiceable'})

    @api.model
    def _smart_timesheeting_cron(self,hourly_offset=0):
        days = hourly_offset//24
        remainder = hourly_offset%24
        now = fields.Datetime.now()

        timesheets = self.search([
            ('project_id', '!=', False),
            ('unit_amount', '>', 0),
            ('date', '>', now - timedelta(days=days+7,hours=remainder)),
            ('date', '<', now - timedelta(days=days,hours=remainder)),
        ])

        for task in timesheets.mapped('task_id'):
            if task.project_id.parent_id:
                parent_project_id = task.project_id.parent_id
            else:
                parent_project_id = task.project_id

            task_ts = timesheets.filtered(lambda t: t.task_id.id == task.id and t.task_id.allow_timesheets)
            for employee in task_ts.mapped('employee_id'):
                #_logger.info("SMART TIMESHEETING: {} on {}".format(task.name,employee.name))
                #we finally create the ts
                self.create({
                    'date': now + timedelta(days=1),
                    'task_id': task.id,
                    'unit_amount': 0.0,
                    'company_id': task.company_id.id,
                    'project_id': task.project_id.id,
                    'main_project_id': parent_project_id.id,
                    'employee_id': employee.id,
                    'name': "Smart Timesheeting",
                })


        """# We look for timesheets of the previous week
        tasks = self.env['project.task'].search([
            ('project_id', '!=', False),
            ('effective_hours', '>', 0),
            ('timesheet_ids.date', '>', fields.Datetime.now() - timedelta(days=7)),
            ('timesheet_ids.date', '<', fields.Datetime.now()),
        ])
        for task in tasks:
            self.create({
                'date': fields.Date.today(),
                'task_id': task.id,
                'amount': 0,
                'company_id': task.company_id,
                'project_id': task.project_id.id,
            })"""

    def _timesheet_preprocess(self, vals):
        vals = super(AnalyticLine, self)._timesheet_preprocess(vals)
        if vals.get('project_id'):
            project = self.env['project.project'].browse(vals['project_id'])
            vals['main_project_id'] = project.id or project.parent_id.id
        return vals

    @api.multi
    def unlink(self):
        for time_sheet in self:
            if time_sheet.timesheet_invoice_id:
                raise ValidationError(_('You cannot delete a timesheet linked to an invoice'))
        return super(AnalyticLine, self).unlink()

    @api.multi
    def _check_can_write(self, values):
        super(AnalyticLine, self)._check_can_write(values)
        if self.filtered(lambda t: t.timesheet_invoice_id):
            if any([field_name in values for field_name in ['unit_amount_rounded']]):
                raise UserError(
                    _('You can not modify already invoiced '
                      'timesheets (linked to a Sales order '
                      'items invoiced on Time and material).')
                )
