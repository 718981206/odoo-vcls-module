# -*- coding: utf-8 -*-

from odoo import models, fields, api

import datetime, pytz
from datetime import datetime,timedelta
import pyodbc

from abc import ABC,abstractmethod


from . import ETL_ACCESS

import logging
_logger = logging.getLogger(__name__)

class KeyNotFoundError(Exception):
    pass

class ETLMap(models.Model):
    _name = 'etl.sync.access.keys'
    _description = 'Odoo ID with external ID'

    odooId = fields.Char(readonly = True,index=True)
    externalId = fields.Char(readonly = True,index=True)
    odooModelName = fields.Char(readonly = True)
    externalObjName = fields.Char(readonly = True)
    lastModifiedExternal = fields.Datetime(readonly = True)
    lastModifiedOdoo = fields.Datetime(readonly = True)
    priority = fields.Integer(default=0)
    
    state = fields.Selection([
        ('upToDate', 'Up To Date'),
        ('needUpdateOdoo', 'Need Update In Odoo'),
        ('needUpdateExternal', 'Need Update In External'),
        ('needCreateOdoo', 'Need To Be Created In Odoo'),
        ('needCreateExternal', 'Need To Be Created In External'),
        ('postponed','Missing Key Info to Process'),
        ],
        string='State',
        default='upToDate' # For existing keys
    )
    migration_running = fields.Boolean()

    @api.one
    def setState(self, state):
        self.state = state
    
    def open_con(self):
        return ETL_ACCESS.ETL_ACCESS.getInstance()
    
    def update_keys(self,params={}):
        _logger.info("ETL | UPDATE KEYS {}".format(params))
        rec_ext = params['accessInstance'].getConnection().execute(params['sql'])
        print(rec_ext)
        keys_exist = self.search([('externalObjName','=',params['externalObjName']),('odooModelName','=',params['odooModelName'])])
        #we default the state of all keys
        keys_exist.write({'state':'upToDate','priority':0})
        keys_exist_sfid = keys_exist.mapped('externalId')
        keys_create = keys_exist.filtered(lambda k: k.externalId and not k.odooId)

        keys_update = self.env['etl.sync.keys']
        keys_to_test=keys_exist.filtered(lambda k: k.externalId and k.odooId)

        #We look for non exisitng keys
        for rec in rec_ext:
            if rec['Id'] not in keys_exist_sfid: #if the rec does not exists

                vals = {
                    'externalObjName':params['externalObjName'],
                    'externalId': rec['Id'],
                    'lastModifiedExternal': datetime.strptime(rec['LastModifiedDate'], "%Y-%m-%dT%H:%M:%S.000+0000"),
                    'odooModelName': params['odooModelName'],
                    'state':'needCreateOdoo',
                }
       
                keys_create |= self.create(vals)
                _logger.info("KEYS | {} New Creation {}".format(params['externalObjName'],vals))

            else: #we ensure not to try to update records we don't have in the rec
                key = keys_to_test.filtered(lambda k: k.externalId==rec['Id'])
                if key:
                    keys_update |= key
                    _logger.info("KEYS | {} To Update {}".format(params['externalObjName'],key.odooId))         
                        
    
        if rec_ext:
            _logger.info("QUERY |\n{}\nreturned {} {} records".format(params['sql'],len(rec_ext),params['externalObjName']))
        if keys_exist:
            _logger.info("KEYS | Found {} existing keys of {}".format(len(keys_exist),params['externalObjName']))

        if keys_create:
            keys_create.write({'state':'needCreateOdoo','priority':params['priority']+1})
            _logger.info("KEYS | {} Keys to create".format(len(keys_create)))
        if keys_update:
            keys_update.write({'state':'needUpdateOdoo','priority':params['priority']})
            _logger.info("KEYS | {} Keys to update".format(len(keys_update)))   

    @api.model
    def access_update_keys(self,obj_dict,is_full_update=True):
        """
        We 1st process the keys and priorities, starting from contacts.
        But then the queue must be executed in revert order of priorities to ensure parent accounts to be created 1st, etc.
        """
        ### PREPARATION
        #Update the context to execute vcls-rdd override
        self.env.user.context_data_integration = True
        #Clean the keys table of corrupted entries
        to_clean = self.search([('odooModelName','=',False),('state','!=','map')])
        #we also clean the ones to create in externals because we don't manage anymore this usecase
        to_clean |= self.search([('externalId','=',False),('state','!=','map')])
        #we also clean the keys not created yet, in order to cover the change in source filtering
        to_clean |= self.search([('odooId','=',False),('state','!=','map')])
        for key in to_clean:
            key.unlink()
        
        #get instance
        accessInstance = self.open_con()

        #make time filter if required
        new_run = datetime.now(pytz.timezone("GMT"))

        time_sql = ""

        self.env.ref('vcls-etl.etl_sf_time_filter').value = time_sql

        ### CLIENTS KEYS PROCESSING
        if obj_dict.get('do_client',False):
            sql = """
                SELECT ClientID FROM tblClient 
                """
            params = {
                'accessInstance':accessInstance,
                'priority':850,
                'externalObjName':'tblClient',
                'sql': sql,
                'odooModelName':'res.partner',
                'is_full_update':True,
            }
            self.update_keys(params)

        ###CLOSING
        #we trigger the processing job

        self.env.ref('vcls-etl.ETL_LastRun').value = new_run.strftime("%Y-%m-%d %H:%M:%S.00+0000")
        self.env.user.context_data_integration = False
    
    def build_sql(self,core,filters=None,post=None):
        sql = core
        if filters:
            for fil in filters:
                if fil != "":
                    if 'WHERE' not in sql:
                        sql += " WHERE " + fil
                    else:
                        sql += " AND " + fil
        if post:
            sql += ' ' + post
            
        return sql

    
    
    @api.model
    def relaunch_cron(self,external_id=None,numbercall=0):
        if external_id:
            cron = self.env.ref(external_id)
            if cron:
                cron.write({
                    'active': True,
                    'nextcall': datetime.now() + timedelta(seconds=10),
                    'numbercall': numbercall,
                })
                _logger.info("ETL | CRON relaunched")





