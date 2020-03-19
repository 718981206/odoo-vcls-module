# -*- coding: utf-8 -*-
import datetime
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, http

from odoo.exceptions import UserError, ValidationError

import logging
_logger = logging.getLogger(__name__)

class MailActivityType(models.Model):
    
    _inherit = 'mail.activity.type'

    default_delay = fields.Integer(
        default = 0,
    )

class MailActivity(models.Model):
    
    _inherit = 'mail.activity'

    lm_ids = fields.Many2many(
        'res.users',
        compute='_get_lm_ids',
        compute_sudo=True,
        store = True,
        )
    
    """default_delay = fields.Integer(
        default = 0,
    )"""

    @api.depends('user_id')  
    def _get_lm_ids(self):
        #Populate a list of authorized user for domain filtering 
        for rec in self:
            if rec.user_id:
                empl = self.env['hr.employee'].search([('user_id','=',rec.user_id.id)],limit=1)
                if empl:
                    rec.lm_ids = empl.lm_ids
                else:
                    rec.lm_ids = False
            else:
                rec.lm_ids = False

    @api.multi
    def open_record(self):
        self.ensure_one()
        url = http.request.env['ir.config_parameter'].get_param('web.base.url')
        link = "{}/web#id={}&model={}".format(url, self.res_id, self.res_model)
        return {
            'type': 'ir.actions.act_url',
            'url': link,
            'target': 'current',
        }
    
    def action_feedback(self, feedback=False):
        # We override to set a safe context and block other tentative of deletion
        self = self.with_context(safe_unlink=True)
        return super(MailActivity, self).action_feedback(feedback)


    @api.multi
    def unlink(self):
        user = self.env['res.users'].browse(self._uid)
        for act in self:
            if not self.env.context.get('safe_unlink', False) and not user.has_group('base.group_system'):
                _logger.info("SAFE UNLINK {} - {}".format(act.res_name,act.user_id.name))
                raise ValidationError("You are not authorized to cancel this activity.")
        return super(MailActivity, self).unlink()
    
    @api.model
    def create(self, values):
        if values.get('activity_type_id'):
            activity_type = self.env['mail.activity.type'].browse(values.get('activity_type_id'))

            if activity_type.default_delay>0 and values.get('date_deadline') == fields.Date.context_today(self):
                #we compute a default deadline value, based on type configuration
                if activity_type.delay_unit == 'days':
                    values['date_deadline'] = fields.Date.context_today(self) + relativedelta(days=activity_type.default_delay)
                elif activity_type.delay_unit == 'weeks':
                    values['date_deadline'] = fields.Date.context_today(self) + relativedelta(weeks=activity_type.default_delay)
                elif activity_type.delay_unit == 'months':
                    values['date_deadline'] = fields.Date.context_today(self) + relativedelta(months=activity_type.default_delay)
                else:
                    pass
            else:
                pass

        return super(MailActivity, self).create(values)
    
    @api.model
    def clean_obsolete(self):
        #we 1st clear the ones related to deleted projects
        self.env.cr.execute("DELETE FROM mail_activity WHERE res_model='project.project' AND res_id not in (SELECT id FROM project_project)")
        self.env.cr.commit()

        """for activity in self.search([]):
            try:
                record = self.env[activity.res_model_id.name].browse(res_id)

            except:
                activity.action_done()
                _logger.info("Mail Activity Deleted")
                #if 'FIELD_NAME' in self.env['product.product']._fields:"""
