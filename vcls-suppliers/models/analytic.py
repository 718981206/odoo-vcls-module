# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

logger = logging.getLogger(__name__)


class AnalyticLine(models.Model):

    _inherit = 'account.analytic.line'

    @api.model
    def _link_portal_analytic_line_purchase(self, user_id):
            self.ensure_one()
            if self.sudo().env.user != self.env.user:
                logger.log(_('This method is only ment to be called with sud privileges'))
            task = self.task_id
            if not task:
                return
            sale_line_id = task.sale_line_id
            if not sale_line_id:
                return
            # look for a purchase line corresponding to this sale line
            purchase_line_obj = self.env['purchase.order.line']
            purchase_obj = self.env['purchase.order']
            purchase_line = purchase_line_obj.search([
                ('is_rebilled', '=', False),
                ('sale_line_id', '=', sale_line_id.id),
                ('partner_id', '=', user_id.partner_id.id),
                ('state', 'not in', ('purchase', 'done', 'cancel')),
            ], limit=1)
            if not purchase_line:
                # create a PO with a line
                purchase_order = purchase_obj.create({
                    'partner_id': self.env.user.partner_id.id,
                })
                values = purchase_line_obj.default_get(
                    list(purchase_line_obj.fields_get()))
                values.update({
                    'sale_line_id': sale_line_id.id,
                    'product_id': sale_line_id.product_id.id,
                    'order_id': purchase_order.id,
                    'account_analytic_id': task.project_id.analytic_account_id.id,
                    # 'date_planned': purchase_order.date_planned,
                })
                purchase_line_cache = purchase_line_obj.new(values)
                purchase_line_cache.onchange_product_id()
                purchase_line_values = purchase_line_cache._convert_to_write({
                    name: purchase_line_cache[name]
                    for name in purchase_line_cache._cache
                })
                purchase_line = purchase_line_obj.create(purchase_line_values)

            purchase_line.is_rebilled = False
            # if the unit is not hours, then qty is time sheet line unit_amount * amount
            uom_is_hours = bool(self.product_uom_id == self.env.ref('uom.product_uom_hour', raise_if_not_found=False))
            if uom_is_hours:
                purchase_line.product_qty = self.unit_amount
            else:
                purchase_line.product_qty *= self.currency_id.compute(self.amount, purchase_line.currency_id)

            # Notify the lead consultant and members of group "Resource Manager"
            users_to_notify = task.project_id.user_id | self.env.ref('vcls-suppliers.vcls_group_rm').users
            for user in users_to_notify:
                self.env['mail.activity'].sudo().create({
                    'res_id': purchase_line.order_id.id,
                    'res_model_id': self.env.ref(
                        'purchase.model_purchase_order').id,
                    'activity_type_id': 4,
                    'user_id': user.id,
                    'summary': _('Please check the purchase order {} for {}.').format(
                        purchase_line.order_id.name, purchase_line.order_id.partner_id.name),
                })
