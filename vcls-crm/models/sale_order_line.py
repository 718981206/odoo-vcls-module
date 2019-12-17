# -*- coding: utf-8 -*-

from odoo import models, fields, tools, api, _
from odoo.exceptions import UserError, ValidationError


class SaleOrderLine(models.Model):

    _inherit = 'sale.order.line'

    # We compute as sudo consultant does not have access to invoices which is required when
    # he logs time from a task
    qty_invoiced = fields.Float(compute_sudo=True)

    vcls_type = fields.Selection(
        related='product_id.vcls_type',
        string="Vcls type",
    )

    # Override the default ordered quantity to be 0 when we order rates items
    product_uom_qty = fields.Float(
        default=0,
    )

    section_line_id = fields.Many2one(
        'sale.order.line',
        string='Line section',
        compute='_get_section_line_id',
        store=False
    )

    ts_invoicing_mode = fields.Selection([('tm', 'T&M'),
                                          ('fp', 'Fixed price')],
                                         'Invoicing mode')

    @api.multi
    def _get_section_line_id(self):
        for line in self:
            order_line_ids = line.order_id.order_line
            current_section_line_id = False
            for order_line_id in order_line_ids:
                if order_line_id.display_type == 'line_section':
                    current_section_line_id = order_line_id
                elif line == order_line_id:
                    line.section_line_id = current_section_line_id
                    break

    def _timesheet_create_project(self):
        project = super(SaleOrderLine, self)._timesheet_create_project()
        project.update({'project_type': 'client'})
        return project

    # We override the line creation in order to link them with existing project
    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        
        for line in lines:
            if (line.product_id.service_tracking in ['project_only', 'task_new_project']) and not line.product_id.project_template_id:
                line.project_id = line.order_id.project_id
        
        return lines

    @api.multi
    def unlink(self):
        for order_line in self:
            if order_line.vcls_type == 'rate':
                related_timesheet = self.env['account.analytic.line'].sudo().search([
                    ('so_line', '=', order_line.id),
                ], limit=1)
                if related_timesheet:
                    raise ValidationError(
                        _('You can not delete the "{}" order line has linked timesheets.'.format(order_line.name))
                    )
                # delete mapping
                related_mapping = self.env['project.sale.line.employee.map'].sudo().search([
                    ('sale_line_id', '=', order_line.id),
                ])
                if related_mapping:
                    related_mapping.sudo().unlink()

            # delete linked forecast
            related_forecasts = self.env['project.forecast'].sudo().search([
                ('order_line_id', '=', order_line.id),
            ])
            
            if related_forecasts:
                related_forecasts.sudo().unlink()
            if order_line.vcls_type == 'vcls_service':
                related_task = self.env['project.task'].sudo().search([
                    '|',
                    ('sale_order_line', '=', order_line.id),
                    ('parent_id.sale_order_line', '=', order_line.id),
                ])
                if related_task:
                    related_task.sudo().unlink()
        return super(SaleOrderLine, self).unlink()
