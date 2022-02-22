from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

import logging

_logger = logging.getLogger(__name__)


class PaymentInvoiceLine(models.Model):
    _name = 'payment.invoice.line'
    
    payment_id = fields.Many2one('account.payment', string="Payment")
    invoice_id = fields.Many2one('account.move', string="Invoice")
    invoice = fields.Char(related='invoice_id.name', string="Invoice Number")
    date = fields.Date(string='Invoice Date', compute='_get_invoice_data', store=True)
    due_date = fields.Date(string='Due Date', compute='_get_invoice_data', store=True)

    base_amount = fields.Float(string='Base Amount', compute='_get_invoice_data', store=True)
    amount_base_tax = fields.Float(string='Amount Tax base', compute='compute_tax_amount', store=True)
    tax_ids_after = fields.Many2many(
        comodel_name='account.tax',
        string='Taxes After',
        context={'active_test': False},
        help="Taxes that apply on the base amount",
        relation='account_tax_after_rel')

    total_amount = fields.Float(string='Total Amount', compute='_get_invoice_data', store=True)
    open_amount = fields.Float(string='Due Amount', compute='_get_invoice_data', store=True)
    allocation = fields.Float(string='Allocation Amount')
    account_move_line_id= fields.Many2one('account.move', string="Invoice")

    

    tax_amount = fields.Float(string='Tax Amount', compute='_get_invoice_data', store=True)
    tax_ids_before = fields.Many2many(
        comodel_name='account.tax',
        string='Taxes Before',
        context={'active_test': False},
        help="Taxes that apply on the base amount",
        relation='account_tax_before_rel')

    amount_total_tax = fields.Float(string='Amount Tax total', compute='compute_tax_total_amount', store=True)
    
    #@api.multi
    @api.depends('invoice_id')
    def _get_invoice_data(self):
        for data in self:
            invoice_id = data.invoice_id
            data.date = invoice_id.invoice_date
            data.due_date = invoice_id.invoice_date_due
            data.total_amount = invoice_id.amount_total
            data.base_amount = invoice_id.amount_untaxed 
            data.tax_amount = round((invoice_id.amount_total - invoice_id.amount_untaxed ), 2)
            data.open_amount = invoice_id.amount_residual


    def cal_tax_ids_before(self):
        for rec in self:     
            for tds_tax in rec.tax_ids_before:
                if rec.payment_id.partner_id and rec.payment_id.partner_id.tds_threshold_check:
                    applicable = self.check_turnover(rec.payment_id.partner_id.id, tds_tax.payment_excess, rec.base_amount)
                tax_repartition_lines = tds_tax.invoice_repartition_line_ids.filtered(
                    lambda x: x.repartition_type == 'tax')
                taxes = tds_tax._origin.compute_all(
                    rec.allocation - rec.tax_amount)
                tds_tax_amount = taxes['total_included'] - taxes[
                    'total_excluded'] if taxes else 0.0
                if applicable:
                    if tds_tax.amount_type == 'group':
                        for child in tds_tax.children_tax_ids:
                            tax_repartition_lines = child.invoice_repartition_line_ids.filtered(
                                lambda x: x.repartition_type == 'tax')
                            taxes = child._origin.compute_all(
                                rec.allocation - rec.tax_amount)
                            tds_tax_amount = taxes['total_included'] - taxes[
                                'total_excluded'] if taxes else 0.0
                            self.payment_id.tds_multi_acc_ids.search([('name', '=', child.name)],limit=1).unlink()
                            self.payment_id.tds_multi_acc_ids.create({
                                'tds_account_id': tax_repartition_lines._origin.id and tax_repartition_lines._origin.account_id.id,
                                'name': child.name,
                                'tax_id': child.id,
                                'amount': tds_tax_amount,
                                'payment_id': rec.payment_id.id,
                                'invoice': rec.invoice,
                                'invoice_id': rec.invoice_id.id
                            })
                    else:               
                        v = self.payment_id.tds_multi_acc_ids.create({
                            'tds_account_id': tax_repartition_lines._origin.id and tax_repartition_lines._origin.account_id.id,
                            'name': tds_tax.name,
                            'tax_id': tds_tax._origin.id,
                            'amount': tds_tax_amount,
                            'payment_id': rec.payment_id.id,
                            'invoice_id': rec.invoice_id.id
                        })
            diff_amount = sum([line.amount for line in rec.payment_id.tds_multi_acc_ids])
            invoice = rec.invoice
            self.env['account.payment'].search([('id','=',rec.payment_id.id)],limit=1).lim_tds_tax_ids(invoice)

    @api.depends('tax_ids_before', 'allocation')
    def compute_tax_total_amount(self):
        for payment in self:
            payment.amount_total_tax = 0.0
            if payment.tax_ids_before and payment.allocation:
                applicable = True
                total_tds_tax_amount = 0.0
                for tax in payment.tax_ids_before:
                    if payment.payment_id.partner_id and payment.payment_id.partner_id.tds_threshold_check:
                        applicable = payment.check_turnover(payment.payment_id.partner_id.id, tax.payment_excess, payment.base_amount)
                    if applicable:
                        taxes = tax._origin.compute_all(
                            payment.allocation - payment.tax_amount)
                        total_tds_tax_amount += taxes['total_included'] - taxes[
                            'total_excluded'] if taxes else 0.0
                        payment.amount_total_tax = total_tds_tax_amount
                    else:
                        payment.amount_total_tax = 0.0
            else:
                payment.amount_total_tax = 0.0

    @api.depends('tax_ids_after', 'total_amount')
    def compute_tax_amount(self):
        for payment in self:
            payment.amount_base_tax = 0.0
            if payment.tax_ids_after and payment.total_amount:
                applicable = True
                total_tds_tax_amount = 0.0
                for tax in payment.tax_ids_after:
                    if payment.payment_id.partner_id and payment.payment_id.partner_id.tds_threshold_check:
                        applicable = payment.check_turnover(payment.payment_id.partner_id.id, tax.payment_excess, payment.total_amount)
                    if applicable:
                        taxes = tax._origin.compute_all(
                            payment.total_amount)
                        total_tds_tax_amount += taxes['total_included'] - taxes[
                            'total_excluded'] if taxes else 0.0
                        payment.amount_base_tax = total_tds_tax_amount
                    else:
                        payment.amount_base_tax = 0.0
            else:
                payment.amount_base_tax = 0.0


    def check_turnover(self, partner_id, threshold, amount):
        for rec in self:
            if rec.payment_id.payment_type == 'outbound':
                domain = [('partner_id', '=', partner_id), ('account_id.internal_type', '=', 'payable'),
                          ('move_id.state', '=', 'posted'), ('account_id.reconcile', '=', True)]
                journal_items = self.env['account.move.line'].search(domain)
                credits = sum([item.credit for item in journal_items])
                credits += amount
                if credits >= threshold:
                    return True
                else:
                    return False
            elif rec.payment_id.payment_type == 'inbound':
                domain = [('partner_id', '=', partner_id), ('account_id.internal_type', '=', 'receivable'),
                          ('move_id.state', '=', 'posted'), ('account_id.reconcile', '=', True)]
                journal_items = self.env['account.move.line'].search(domain)
                debits = sum([item.debit for item in journal_items])
                debits += amount
                if debits >= threshold:
                    return True
                else:
                    return False