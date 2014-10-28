# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp.osv import osv, fields
from at_base import helper
from openerp.tools.translate import _
from at_base.format import LangFormat
from at_base import util

class commission_invoice_wizard(osv.osv_memory):
    
    def _name_default(self,cr,uid,context=None):
        date_min = None
        date_max = None
        commission_line_obj = self.pool.get("at_commission.line")
        
        for line in commission_line_obj.browse(cr, uid, 
                                               util.active_ids(context, commission_line_obj), 
                                               context=context):
            if not date_min or line.period_id.date_start < date_min:
                date_min = line.period_id.date_start
            if not date_max or line.period_id.date_stop > date_max:
                date_max = line.period_id.date_stop
        return _("Provision %s") % (helper.getRangeName(cr, uid, date_min, date_max,context),)
      
    def _inv_line_name_get(self,cr,uid,wizard,analytic_line,context=None):
        f = LangFormat(cr, uid, context=context)
        infos = []
        if analytic_line:
            if analytic_line.date:
                infos.append(f.formatLang(analytic_line.date,date=True))
            if analytic_line.ref:
                infos.append(analytic_line.ref)
            if wizard.related_invoice and analytic_line.invoice_id and analytic_line.invoice_id.number:
                infos.append(analytic_line.invoice_id.number)
            if analytic_line.name:
                infos.append(analytic_line.name)
        #       
        return " / ".join(infos) or ""
      
    def _inv_line_note_get(self,cr,uid,wizard,analytic_line,context=None):
        f = LangFormat(cr, uid, context=context)
        cur = analytic_line.currency_id.symbol or analytic_line.currency_id.name or ""
        
        if analytic_line.base_commission == analytic_line.total_commission:
            return _("%s %% Commission from %s %s") % (analytic_line.base_commission,f.formatLang(analytic_line.price_sub, dp="Sale Price"),cur)
        elif analytic_line.base_commission < analytic_line.total_commission:
            return _("%s %% Commission +%s %% Bonus from %s %s") % (analytic_line.base_commission,
                                                                                analytic_line.total_commission-analytic_line.base_commission, 
                                                                                f.formatLang(analytic_line.price_sub, dp="Sale Price"),cur)
        else:
            return _("%s %% Commission -%s %% Malus from %s %s") % (analytic_line.base_commission,
                                                                                analytic_line.base_commission-analytic_line.total_commission, 
                                                                                f.formatLang(analytic_line.price_sub, dp="Sale Price"),cur)
            
    def do_create(self,cr,uid,ids,context=None):
        invoice_line_obj = self.pool.get("account.invoice.line")
        invoice_obj = self.pool.get("account.invoice")
        fiscal_pos_obj = self.pool.get("account.fiscal.position")
        partner_obj = self.pool.get("res.partner")
        commission_line_obj = self.pool.get("at_commission.line")
        journal_obj = self.pool.get("account.journal")
        wizard = self.browse(cr, uid, ids[0], context)        
        #
        partner = None
        account_position = None
        invoice_ids = []
        #        
        line_ids = commission_line_obj.search(cr,uid,[("id","in",util.active_ids(context))],order="partner_id")        
        for line in commission_line_obj.browse(cr, uid, line_ids):
            # group partners
            if not partner or partner.id != line.partner_id.id:
                partner = line.partner_id                
                account_position = partner.property_account_position
                company = line.company_id
                #
                journal_ids = journal_obj.search(cr, uid, [('type', '=','purchase'),('company_id', '=', company.id)], limit=1)
                if not journal_ids:
                    raise osv.except_osv(_('Error !'),
                        _('There is no purchase journal defined for this company: "%s" (id:%d)') % (company.name, company.id))
                  
                #   
                inv_values = {
                  "type" : "in_invoice",
                  "name" : wizard.name,
                  "reference" : wizard.name,
                  "origin" : wizard.name,
                  "partner_id" : partner.id,
                  "address_contact_id" :  partner_obj.address_get(cr, uid,[partner.id], adr_pref=["contact"])["contact"],
                  "address_invoice_id" :  partner_obj.address_get(cr, uid,[partner.id], adr_pref=["invoice"])["invoice"],
                  "payment_term" : partner.property_payment_term.id or False,
                  "journal_id" : journal_ids[0],
                  "account_id" : partner.property_account_receivable.id,
                  "currency_id" : line.currency_id.id or company.currency_id.id or None,
                  "payment_term" : partner.property_payment_term and partner.property_payment_term.id or False,
                  "company_id" : company.id,
                  "fiscal_position" : account_position.id
                }
                invoice_id = invoice_obj.create(cr,uid,inv_values,context=context)
                #
                invoice_ids.append(invoice_id)

            product = line.product_id                    
            taxes = product.taxes_id
            tax = fiscal_pos_obj.map_tax(cr, uid, account_position, taxes)
            
            values = {
                "invoice_id" : invoice_id,
                "price_unit" : line.amount,
                "quantity" : line.unit_amount,
                "invoice_line_tax_id" : tax,
                "name" : line.name,                
                "product_id" : product.id,               
                "uos_id" : line.product_uom_id.id,
                "account_id" : line.general_account_id.id,
                "account_analytic_id" : line.account_id.id
            }
            #            
            
            chg_values = invoice_line_obj.product_id_change(cr, uid,[],
                                               values["product_id"],
                                               values["uos_id"],
                                               values["quantity"],
                                               values["name"],
                                               inv_values["type"],
                                               inv_values["partner_id"],
                                               inv_values["fiscal_position"],
                                               values["price_unit"],
                                               inv_values["address_invoice_id"],
                                               inv_values["currency_id"],
                                               context=context)
            
            chg_values=chg_values["value"]
            chg_values["invoice_line_tax_id"]=chg_values["invoice_line_tax_id"] and [(6,0,chg_values["invoice_line_tax_id"])] or None 
            
            values.update(chg_values)         
            values["name"] = self._inv_line_name_get(cr, uid, wizard, line, context)            
            values["note"] = self._inv_line_note_get(cr, uid, wizard, line, context)               
            invoice_line_id = invoice_line_obj.create(cr,uid,values,context=context)
            #            
            commission_line_obj.write(cr,uid,line.id,{"invoiced_id" : invoice_id,
                                                      "invoiced_line_ids" : [(4,invoice_line_id)]
                                                      })
        
        # update invoices                       
        if invoice_ids:
            #
            invoice_obj.button_compute(cr, uid, invoice_ids, {'type':'in_invoice'}, set_total=True)
            #
            # Show Invoices
            #
            mod_obj = self.pool.get("ir.model.data")
            act_obj = self.pool.get("ir.actions.act_window")
            #
            mod_ids = mod_obj.search(cr, uid, [("name", "=", "action_invoice_tree2")], context=context)[0]
            res_id = mod_obj.read(cr, uid, mod_ids, ["res_id"], context=context)["res_id"]
            act_win = act_obj.read(cr, uid, res_id, [], context=context)
            act_win["domain"] = [("id","in",invoice_ids),("type","=","in_invoice")]            
            return act_win
        #or nothing
        return { "type" : "ir.actions.act_window_close" }
    
    _name = "at_commission.commission_invoice_wizard"
    _description = "Create invoice from commission"

    _columns = {
        "name" : fields.char("Description",size=64),        
        "related_invoice" : fields.boolean("Related Invoice", help="The related invoice will be displayed")
    }
    _defaults = {
        "name" : _name_default
    }
commission_invoice_wizard()
