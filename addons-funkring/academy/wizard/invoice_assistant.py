# -*- coding: utf-8 -*-
#############################################################################
#
#    Copyright (c) 2007 Martin Reisenhofer <martin.reisenhofer@funkring.net>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp.osv import fields, osv
from openerp.addons.at_base import util

class academy_invoice_assistant(osv.osv_memory):
    
    def onchange_semester(self, cr, uid, ids, semester_id, context=None):
        values = {}
        res = { "value" : values }
        
        if semester_id:
            values["customer_ref"] = self.pool["academy.semester"].name_get(cr, uid, [semester_id], context=context)[0][1]
            
        return res
        
    def action_invoice(self, cr, uid, ids, context=None):
        invoice_obj = self.pool["account.invoice"]
        invoice_line_obj = self.pool["account.invoice.line"]
        reg_obj = self.pool["academy.registration"]
        reg_inv_obj = self.pool["academy.registration.invoice"]

        wizard = self.browse(cr, uid, ids[0], context=context)
        semester = wizard.semester_id
        
        # registration query filter
        reg_query = []
        sel_reg_ids = util.active_ids(context,"academy.registration")
        if sel_reg_ids:
            reg_query.append(("id","in",sel_reg_ids))
            
        # state filter
        reg_query.append("!")
        reg_query.append(("state","in",["draft","cancel","check"]))
        
        # search valid registration ids
        reg_ids = reg_obj.search(cr, uid, reg_query)
        
        # group registrations
        invoices = {}        
        for reg in reg_obj.browse(cr, uid, reg_ids, context=context):
            student = reg.student_id            
            parent = student.parent_id
            
            
            # check if invoice for registration exist
            reg_inv_id = reg_inv_obj.search_id(cr, uid, [("registration_id","=",reg.id),("semester_id","=",semester.id)], context=context)
            if reg_inv_id:
                continue
            
            invoice_address = reg.use_invoice_address_id
            invoice = invoices.get(invoice_address.id)
            if not invoice:
                invoice = ( invoice_address, [] )
                invoices[invoice_address.id] = invoice

            invoice[1].append(reg)
            
        # create invoices
        for partner, registrations in invoices.itervalues():
            # invoice context
            inv_context = context and dict(context) or {}
            inv_context["type"] = "out_invoice"

            # invoice values            
            inv_values = {
                "partner_id" : partner.id,
                "name" : wizard.customer_ref
            }            
            inv_values.update(invoice_obj.onchange_partner_id(cr, uid, [], "out_invoice", partner.id, context=context)["value"])
            invoice_id = invoice_obj.create(cr, uid, inv_values, context=context)
            invoice = invoice_obj.browse(cr, uid, invoice_id, context=context)
                        
            def addProduct(product, uos_id=None, discount=0.0):
                line = { "invoice_id" : invoice_id,
                          "product_id" : product.id,
                          "quantity" : 1.0,
                          "uos_id" : uos_id or product.uos_id.id
                        }
                line.update(invoice_line_obj.product_id_change(cr, uid, [],
                                line["product_id"], line["uos_id"], qty=line["quantity"],
                                type=invoice.type, 
                                partner_id=invoice.partner_id.id, 
                                fposition_id=invoice.fiscal_position.id, 
                                company_id=invoice.company_id.id, 
                                currency_id=invoice.currency_id.id,
                                context=inv_context)["value"])
                
                tax_ids = line.get("invoice_line_tax_id")
                if tax_ids:
                    line["invoice_line_tax_id"]=[(6,0,tax_ids)]
                return invoice_line_obj.create(cr, uid, line, context=context)
                
            
            # create lines
            for reg in registrations:
                # create line
                addProduct(reg.course_prod_id.product_id, reg.uom_id.id)
                
                # create invoice link
                reg_inv_obj.create(cr, uid, { "registration_id" : reg.id,
                                              "semester_id" : semester.id,
                                              "invoice_id" : invoice_id})
                
                rent_product = reg.location_id.rent_product_id
                if rent_product:
                    cr.execute(" SELECT COUNT(l.id) FROM account_invoice_line l "
                               " INNER JOIN account_invoice inv ON inv.id = l.invoice_id "
                               " INNER JOIN academy_registration_invoice rinv ON rinv.invoice_id = inv.id AND rinv.semester_id = %s "
                               " INNER JOIN academy_registration r ON r.id = rinv.id "
                               " INNER JOIN academy_student s ON s.id = r.student_id "
                               " INNER JOIN res_partner p ON p.id = s.partner_id "
                               " WHERE l.product_id = %s AND p.parent_id = %s AND l.amount > 0 AND l.discount < 100",
                                (semester.id, rent_product.id, parent.id) )
                    
                    rows = cr.fetchone()       
                    rent_invoiced = rows and rows[0]
                    
                    # add discount if rent was already invoiced
                    discount = 0.0
                    if rent_invoiced:
                       discount = 100.0
                       
                    addProduct(rent_product, discount=discount)
                    
            
            # validate invoice
            invoice_obj.button_compute(cr, uid, [invoice_id], context=context)
        
        return { "type" : "ir.actions.act_window_close" }
    
    def _default_semester_id(self, cr, uid, fields, context=None):
        user = self.pool["res.users"].browse(cr, uid, uid, context=context)
        return user.company_id.academy_semester_id.id

    _name = "academy.invoice.assistant"
    _columns = {
        "semester_id" : fields.many2one("academy.semester", "Semester", required=True),
        "customer_ref" : fields.char("Reference")
    }
    _defaults = {
        "semester_id" : _default_semester_id
    }
