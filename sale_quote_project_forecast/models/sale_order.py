# Copyright 2019 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models, api, _, fields
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_sync(self):
        self.mapped('order_line').sudo().with_context(
            default_company_id=self.company_id.id,
            force_company=self.company_id.id,
        )._timesheet_service_generation()
        milestone_tasks = self.get_milestone_tasks()
        rate_order_lines = self.get_rate_tasks()
        for order_line in rate_order_lines:
            for task in milestone_tasks:
                employee = order_line.product_id.forecast_employee_id
                sen_level = order_line.product_id.seniority_level_id
                if not employee:
                    employee = self.env['hr.employee'].search(
                        [('seniority_level_id', '=', sen_level)], limit=1)
                if not employee:
                    raise UserError(
                        _("No Employee available for Seniority level \
                        {}").format(sen_level.name)
                    )
                existing = self.env['project.forecast'].search([
                    ('project_id', '=', task.project_id.id),
                    ('task_id', '=', task.id),
                    ('employee_id', '=', employee.id)
                ])
                if not existing:
                    self.env['project.forecast'].create({
                        'project_id': task.project_id.id,
                        'task_id': task.id,
                        'employee_id': employee.id
                    })
            employee = order_line.product_id.forecast_employee_id
            project = self.mapped('tasks_ids.project_id')
            if len(project) == 1:
                existing = self.env['project.sale.line.employee.map'].search([
                    ('project_id', '=', project.id),
                    ('sale_line_id', '=', order_line.id),
                    ('employee_id', '=', employee.id)
                ])
                if not existing:
                    self.env['project.sale.line.employee.map'].create({
                        'project_id': project.id,
                        'sale_line_id': order_line.id,
                        'employee_id': employee.id,
                    })

    @api.multi
    def get_milestone_tasks(self):
        order_lines = self.order_line.filtered(
            lambda r: r.product_id.type == 'service' and
            r.product_id.service_policy == 'delivered_manual' and
            r.product_id.service_tracking == 'task_new_project'
        )
        return order_lines.mapped('task_id')

    @api.multi
    def get_rate_tasks(self):
        order_lines = self.order_line.filtered(
            lambda r: r.product_id.type == 'service' and
            r.product_id.service_policy == 'delivered_timesheet' and
            r.product_id.service_tracking in ('no', 'project_only')
        )
        return order_lines
    
    @api.multi
    def upsell(self):
        for rec in self:
            new_order = rec.copy({'order_line': False})

            #we copy the project_ids to properly link newly created tasks
            _logger.info("New Upsell: {} Found Projects: {}".format(new_order.name,rec.project_ids.mapped('name')))
            new_order.project_ids = rec.project_ids
            pending_section = None

            #we loop in source lines to copy rate ones only
            for line in rec.order_line:
                if line.display_type == 'line_section':
                    pending_section = line
                    continue
                elif line.product_id.type == 'service' and \
                    line.product_id.service_policy == 'delivered_timesheet' and \
                    line.product_id.service_tracking in ('no', 'project_only'):
                    if pending_section:
                        pending_section.copy({'order_id': new_order.id})
                        pending_section = None
                    line.copy({'order_id': new_order.id,
                               'project_id': line.project_id.id,
                               'analytic_line_ids': [(6, 0, line.analytic_line_ids.ids)]})
        return {
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'sale.order',
                'target': 'current',
                'res_id': new_order.id,
            }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    service_policy = fields.Selection(
        'Service Policy',
        related='product_id.service_policy',
        readonly=True,
    )
