from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

import logging

_logger = logging.getLogger(__name__)  


class account_payment(models.Model):
    _inherit = 'account.payment'
    
    invoice_lines = fields.One2many('payment.invoice.line', 'payment_id', string="Invoice Line")
    multipagos = fields.Boolean(
        string='Multipagos', default=True
    )

    tds_multi_acc_ids = fields.One2many('tds.accounts', 'payment_id', string='Write Off Accounts')
   
    def update_invoice_lines(self):
        if self.payment_type == 'inbound':
            for inv in self.invoice_lines:
                inv.open_amount = inv.invoice_id.amount_residual 
            self.onchange_partner_id()

    def action_draft(self):
        for rec in self:
            moves = rec.mapped('move_line_ids.move_id')
            moves.filtered(lambda move: move.state == 'posted').button_draft()
            moves.with_context(force_delete=True).unlink()
            rec.write({'state': 'draft','name':False,'move_name':''})

    def tax_ids_befores(self):
        self.invoice_lines.cal_tax_ids_before()

    def lim_tds_tax_ids(self,invoice):
        taxs = self.env['tds.accounts'].search([('payment_id','=',self.id),('invoice','=',invoice)])
        val = []
        invo = []
        for lin in taxs:
            val.append(lin.name)
            invo.append(lin.invoice)
        invoice = set(invo)
        vals = set(val)
        for l in vals:
            tax_count = self.env['tds.accounts'].search_count([('name','=',l),('payment_id','=',self.id),('invoice','=',invoice)])
            if tax_count > 1:                
                tax = self.env['tds.accounts'].search([('name','=',l),('payment_id','=',self.id),('invoice','=',invoice)],limit=1)
                for t in tax:
                    t.write({'repeat': True})
        self.remove_repeats(invoice)

    def remove_repeats(self,invoice):
        taxs = self.env['tds.accounts'].search([('payment_id','=',self.id),('repeat','=',True),('invoice','=',invoice)]).unlink()


    #we could add another line with a comparation between amount_residual > 0
    @api.onchange('partner_id', 'currency_id')
    def onchange_partner_id(self):
        if self.payment_type in ['inbound','outbound']:
            if self.partner_id and self.payment_type != 'transfer' and self.multipagos == True:
                vals = {}
                line = [(6, 0, [])]
                invoice_ids = []
                if self.payment_type == 'outbound' and self.partner_type == 'supplier':
                    invoice_ids = self.env['account.move'].search([('partner_id', 'in', [self.partner_id.id]),
                                                                      ('state', '=','posted'),
                                                                      ('amount_residual','>',0.0),
                                                                      ('type','=','in_invoice'),
                                                                      ('currency_id', '=', self.currency_id.id)])

                if self.payment_type == 'inbound' and self.partner_type == 'supplier':
                    invoice_ids = self.env['account.move'].search([('partner_id', 'in', [self.partner_id.id]),
                                                                      ('state', '=','posted'),
                                                                      ('amount_residual','>',0.0),
                                                                      ('type','=', 'in_refund'),
                                                                      ('currency_id', '=', self.currency_id.id)])

                if self.payment_type == 'inbound' and self.partner_type == 'customer':
                    invoice_ids = self.env['account.move'].search([('partner_id', 'in', [self.partner_id.id]),
                                                                      ('state', '=','posted'),
                                                                      ('amount_residual','>',0.0),
                                                                      ('type','=','out_invoice'),
                                                                      ('currency_id', '=', self.currency_id.id)])

                if self.payment_type == 'outbound' and self.partner_type == 'customer':
                    invoice_ids = self.env['account.move'].search([('partner_id', 'in', [self.partner_id.id]),
                                                                      ('state', '=','posted'),
                                                                      ('amount_residual','>',0.0),
                                                                      ('type','=','out_refund'),
                                                                      ('currency_id', '=', self.currency_id.id)])
                
                for inv in invoice_ids[::-1]:
                    vals = {
                           'invoice_id': inv.id,
                           }
                    
                    line.append((0, 0, vals))
                self.invoice_lines = line
                self.onchnage_amount()
            if self.partner_id and self.payment_type != 'transfer' and self.multipagos == False:
                vals = {}
                line = [(6, 0, [])]
                invoice_ids = []
                if self.payment_type == 'outbound' and self.partner_type == 'supplier':
                    invoice_ids = self.env['account.move'].search([('name', '=', self.communication)])

                if self.payment_type == 'inbound' and self.partner_type == 'supplier':
                    invoice_ids = self.env['account.move'].search([('name', '=', self.communication)])

                if self.payment_type == 'inbound' and self.partner_type == 'customer':
                    invoice_ids = self.env['account.move'].search([('name', '=', self.communication)])

                if self.payment_type == 'outbound' and self.partner_type == 'customer':
                    invoice_ids = self.env['account.move'].search([('name', '=', self.communication)])

                for inv in invoice_ids[::-1]:
                    vals = {
                           'invoice_id': inv.id,
                           }
                    
                    line.append((0, 0, vals))
                self.invoice_lines = line
                self.onchnage_amount()
        
    @api.onchange('payment_type')
    def _onchange_payment_type(self):
        if self.payment_type == 'transfer':
            self.invoice_lines = [(6, 0, [])]
            
        if not self.invoice_ids:
            # Set default partner type for the payment type
            if self.payment_type == 'inbound':
                self.partner_type = 'customer'
            elif self.payment_type == 'outbound':
                self.partner_type = 'supplier'
        # Set payment method domain
        res = self._onchange_journal()
        if not res.get('domain', {}):
            res['domain'] = {}
        res['domain']['journal_id'] = self.payment_type == 'inbound' and [('at_least_one_inbound', '=', True)] or [('at_least_one_outbound', '=', True)]
        res['domain']['journal_id'].append(('type', 'in', ('bank', 'cash')))
        return res
    
    @api.onchange('amount')
    def onchnage_amount(self):
        total = 0.0
        remain = self.amount
        for line in self.invoice_lines:
            if line.open_amount <= remain:
                line.allocation = line.open_amount
                remain -= line.allocation
            else:
                line.allocation = remain
                remain -= line.allocation
            total += line.allocation

    def line_value(self):
        for rec in self:
            if rec.invoice_lines:
                amount = 0
                for line in rec.invoice_lines:
                    amount += line.allocation
                if round(amount, 2) != rec.amount:
                    raise UserError(_("El total de las lineas excede el total del pago %s.") % (amount,))

    def clean_lines(self):
        for rec in self:
            if rec.invoice_lines:
                for line in rec.invoice_lines:
                    if line.allocation == 0.0:
                        line.unlink()


    def tds_tax_call(self):
        self.write({'tds_multi_acc_ids':[(5,0,0)]})
        if not self._context.get('active_model'):
            return False
        amount_res = self.invoice_ids and self.invoice_ids[0].amount_residual
        applicable = False
        for x in payment.invoice_lines:
            for tds_tax in x.tax_ids_before:
                active_id = self._context.get('active_id')
                move = self.env['account.move'].browse(active_id)
                if move.partner_id and move.partner_id.tds_threshold_check:
                    applicable = self.check_turnover(move.partner_id.id, tds_tax.payment_excess, x.allocation)
                tax_repartition_lines = tds_tax.invoice_repartition_line_ids.filtered(
                    lambda x: x.repartition_type == 'tax')
                taxes = tds_tax._origin.compute_all(
                    amount_res)
                tds_tax_amount = taxes['total_included'] - taxes[
                    'total_excluded'] if taxes else 0.0
                if applicable:
                    if tds_tax.amount_type == 'group':
                        for child in tds_tax.children_tax_ids:
                            tax_repartition_lines = child.invoice_repartition_line_ids.filtered(
                                lambda x: x.repartition_type == 'tax')
                            taxes = child._origin.compute_all(
                                self.amount)
                            tds_tax_amount = taxes['total_included'] - taxes[
                                'total_excluded'] if taxes else 0.0
                            self.tds_multi_acc_ids.create({
                                'tds_account_id': tax_repartition_lines._origin.id and tax_repartition_lines._origin.account_id.id,
                                'name': child.name,
                                'tax_id': child.id,
                                'amount': tds_tax_amount,
                                'payment_id': self.id
                            })
                    else:
                        self.tds_multi_acc_ids.create({
                            'tds_account_id': tax_repartition_lines._origin.id and tax_repartition_lines._origin.account_id.id,
                            'name': tds_tax.name,
                            'tax_id': tds_tax._origin.id,
                            'amount': tds_tax_amount,
                            'payment_id': self.id
                        })
            diff_amount = sum([line.amount for line in self.tds_multi_acc_ids])
      


    #@api.multi
    def post(self):
        """ Create the journal items for the payment and update the payment's state to 'posted'.
            A journal entry is created containing an item in the source liquidity account (selected journal's default_debit or default_credit)
            and another in the destination reconcilable account (see _compute_destination_account_id).
            If invoice_ids is not empty, there will be one reconcilable move line per invoice to reconcile with.
            If the payment is a transfer, a second journal entry is created in the destination journal to receive money from the transfer account.
        """
        print("zzzzzzz")
        self.tax_ids_befores()
        for rec in self:
            amt = 0
            if rec.invoice_lines and rec.payment_type in ['inbound','outbound']:
                print("xxxxx1111")
                AccountMove = self.env['account.move'].with_context(default_type='entry')
                if rec.invoice_lines:
                     
                    amt = 0
                    if rec.invoice_lines:
                         
                        for line in rec.invoice_lines:
                            amt += line.allocation
                        val = round(amt,2)
                        if rec.amount < val:
                            raise ValidationError(("El monto del pago debe ser mayor o igual a '%s'") %(val))
                        if rec.amount > val:
                            for line in rec.invoice_lines:
                                line.allocation = line.allocation + (rec.amount - val)
                                raise ValidationError(("El monto de la linea supera el adeudo '%s'") %(val))

                    if rec.state != 'draft':
                        raise UserError(_("Only a draft payment can be posted."))

                    if any(inv.state != 'posted' for inv in rec.invoice_ids):
                        raise ValidationError(_("The payment cannot be processed because the invoice is not open!"))

                    # keep the name in case of a payment reset to draft
                    if not rec.name:
                        # Use the right sequence to set the name
                        if rec.payment_type == 'transfer':
                            sequence_code = 'account.payment.transfer'
                        else:
                            if rec.partner_type == 'customer':
                                if rec.payment_type == 'inbound':
                                    sequence_code = 'account.payment.customer.invoice'
                                if rec.payment_type == 'outbound':
                                    sequence_code = 'account.payment.customer.refund'
                            if rec.partner_type == 'supplier':
                                if rec.payment_type == 'inbound':
                                    sequence_code = 'account.payment.supplier.refund'
                                if rec.payment_type == 'outbound':
                                    sequence_code = 'account.payment.supplier.invoice'
                        rec.name = self.env['ir.sequence'].next_by_code(sequence_code, sequence_date=rec.payment_date)
                        if not rec.name and rec.payment_type != 'transfer':
                            raise UserError(_("You have to define a sequence for %s in your company.") % (sequence_code,))

                    moves = AccountMove.create(rec._prepare_payment_moves())
                    for x in moves:
                        for l in x.line_ids:
                            for lin in rec.invoice_lines:
                                if lin.invoice_id.id == l.invoice_id.id and l.credit > 0:
                                    lin.write({'account_move_line_id': x.id})
                    if rec.invoice_lines:
                        self.invoice_ids = self.invoice_lines.mapped('invoice_id')
                    moves.filtered(lambda move: move.journal_id.post_at != 'bank_rec').post()
                    
                    # Update the state / move before performing any reconciliation.
                    move_name = self._get_move_name_transfer_separator().join(moves.mapped('name'))
                    rec.write({'state': 'posted', 'move_name': move_name})

                    if rec.payment_type in ('inbound', 'outbound'):
                        # ==== 'inbound' / 'outbound' ====
                        if rec.invoice_ids:
                            # (moves[0] + rec.invoice_ids).line_ids \
                            #     .filtered(lambda line: not line.reconciled and line.account_id == rec.destination_account_id)\
                            #     .reconcile()
                            if rec.multipagos == True:
                                for x in rec.invoice_lines:                       
                                    (x.invoice_id + x.account_move_line_id).line_ids \
                                    .filtered(lambda line: not line.reconciled and line.account_id == rec.destination_account_id)\
                                    .reconcile()
                            else:
                                (moves[0] + rec.invoice_ids).line_ids \
                                .filtered(lambda line: not line.reconciled and line.account_id == rec.destination_account_id)\
                                .reconcile()


                    elif rec.payment_type == 'transfer':
                        # ==== 'transfer' ====
                        moves.mapped('line_ids')\
                            .filtered(lambda line: line.account_id == rec.company_id.transfer_account_id)\
                            .reconcile()
            else:
                print("xxxxx22222")
                return super(account_payment, self).post()                
        self.line_value()
        self.clean_lines()
        return True

    
            

    def _prepare_payment_moves(self):
        for rec in self:
            if rec.invoice_lines and self.payment_type in ('outbound', 'inbound'):
                return rec._prepare_payment_moves_xmarts()
            else:
                return super(account_payment, self)._prepare_payment_moves()


    def _prepare_payment_moves_xmarts(self):
        ''' Prepare the creation of journal entries (account.move) by creating a list of python dictionary to be passed
        to the 'create' method.

        Example 1: outbound with write-off:

        Account             | Debit     | Credit
        ---------------------------------------------------------
        BANK                |   900.0   |
        RECEIVABLE          |           |   1000.0
        WRITE-OFF ACCOUNT   |   100.0   |

        Example 2: internal transfer from BANK to CASH:

        Account             | Debit     | Credit
        ---------------------------------------------------------
        BANK                |           |   1000.0
        TRANSFER            |   1000.0  |
        CASH                |   1000.0  |
        TRANSFER            |           |   1000.0

        :return: A list of Python dictionary to be passed to env['account.move'].create.
        '''
        self.line_value()
        self.clean_lines()
        all_move_vals = []
        for payment in self:
            for x in payment.invoice_lines:
                company_currency = payment.company_id.currency_id
                move_names = payment.move_name.split(payment._get_move_name_transfer_separator()) if payment.move_name else None

                # Compute amounts.
                write_off_amount = payment.payment_difference_handling == 'reconcile' and -payment.payment_difference or 0.0
                if payment.payment_type in ('outbound', 'transfer'):
                    counterpart_amount = x.allocation
                    liquidity_line_account = payment.journal_id.default_debit_account_id
                else:
                    counterpart_amount = -x.allocation
                    liquidity_line_account = payment.journal_id.default_credit_account_id

                # Manage currency.
                if payment.currency_id == company_currency:
                    # Single-currency.
                    balance = counterpart_amount
                    write_off_balance = write_off_amount
                    counterpart_amount = write_off_amount = 0.0
                    currency_id = False
                else:
                    # Multi-currencies.
                    balance = payment.currency_id._convert(counterpart_amount, company_currency, payment.company_id, payment.payment_date)
                    write_off_balance = payment.currency_id._convert(write_off_amount, company_currency, payment.company_id, payment.payment_date)
                    currency_id = payment.currency_id.id

                # Manage custom currency on journal for liquidity line.
                if payment.journal_id.currency_id and payment.currency_id != payment.journal_id.currency_id:
                    # Custom currency on journal.
                    if payment.journal_id.currency_id == company_currency:
                        # Single-currency
                        liquidity_line_currency_id = False
                    else:
                        liquidity_line_currency_id = payment.journal_id.currency_id.id
                    liquidity_amount = company_currency._convert(
                        balance, payment.journal_id.currency_id, payment.company_id, payment.payment_date)
                else:
                    # Use the payment currency.
                    liquidity_line_currency_id = currency_id
                    liquidity_amount = counterpart_amount

                # Compute 'name' to be used in receivable/payable line.
                rec_pay_line_name = ''
                if payment.payment_type == 'transfer':
                    rec_pay_line_name = payment.name
                else:
                    if payment.partner_type == 'customer':
                        if payment.payment_type == 'inbound':
                            rec_pay_line_name += _("Customer Payment")
                        elif payment.payment_type == 'outbound':
                            rec_pay_line_name += _("Customer Credit Note")
                    elif payment.partner_type == 'supplier':
                        if payment.payment_type == 'inbound':
                            rec_pay_line_name += _("Vendor Credit Note")
                        elif payment.payment_type == 'outbound':
                            rec_pay_line_name += _("Vendor Payment")
                    if payment.invoice_ids:
                        rec_pay_line_name += ': %s' % ', '.join(payment.invoice_ids.mapped('name'))

                # Compute 'name' to be used in liquidity line.
                if payment.payment_type == 'transfer':
                    liquidity_line_name = _('Transfer to %s') % payment.destination_journal_id.name
                else:
                    liquidity_line_name = payment.name

                # ==== 'inbound' / 'outbound' ====
                if x.tax_ids_before:
                    amount_total_tax = 0.0
                    if x.tax_ids_before and x.allocation:
                        applicable = True
                        total_tds_tax_amount = 0.0
                        for tax in x.tax_ids_before:
                            if x.payment_id.partner_id and x.payment_id.partner_id.tds_threshold_check:
                                applicable = x.check_turnover(x.payment_id.partner_id.id, tax.payment_excess, x.allocation)
                            if applicable:
                                taxes = tax._origin.compute_all(
                                    x.allocation - x.tax_amount)
                                total_tds_tax_amount += taxes['total_included'] - taxes[
                                    'total_excluded'] if taxes else 0.0
                                amount_total_tax = total_tds_tax_amount
                            else:
                                amount_total_tax = 0.0
                    if payment.payment_type == 'outbound' and payment.partner_type == 'supplier':
                        move_vals = {
                            'date': payment.payment_date,
                            'ref': payment.communication,
                            'journal_id': payment.journal_id.id,
                            'currency_id': payment.journal_id.currency_id.id or payment.company_id.currency_id.id,
                            'partner_id': payment.partner_id.id,
                            'line_ids': [
                                # Receivable / Payable / Transfer line.
                                (0, 0, {
                                    'name': rec_pay_line_name,
                                    'amount_currency': counterpart_amount + write_off_amount if currency_id else 0.0,
                                    'currency_id': currency_id,
                                    'debit': balance + write_off_balance > 0.0 and balance + write_off_balance or 0.0,
                                    'credit': balance + write_off_balance < 0.0 and -balance - write_off_balance or 0.0,
                                    'date_maturity': payment.payment_date,
                                    'partner_id': payment.partner_id.id,
                                    'account_id': payment.destination_account_id.id,
                                    'payment_id': payment.id,
                                    'invoice_id': x.invoice_id.id,
                                }),
                                # Liquidity line.
                                (0, 0, {
                                    'name': liquidity_line_name,
                                    'amount_currency': -liquidity_amount if liquidity_line_currency_id else 0.0,
                                    'currency_id': liquidity_line_currency_id,
                                    'debit': balance < 0.0 and -balance or 0.0,
                                    'credit': round((balance + total_tds_tax_amount),2) > 0.0 and round((balance +total_tds_tax_amount),2) or 0.0,
                                    'date_maturity': payment.payment_date,
                                    'partner_id': payment.partner_id.id,
                                    'account_id': liquidity_line_account.id,
                                    'payment_id': payment.id,
                                    'invoice_id': x.invoice_id.id,
                                }),
                            ],
                        }
                    if payment.payment_type == 'inbound' and payment.partner_type == 'customer':
                        move_vals = {
                            'date': payment.payment_date,
                            'ref': payment.communication,
                            'journal_id': payment.journal_id.id,
                            'currency_id': payment.journal_id.currency_id.id or payment.company_id.currency_id.id,
                            'partner_id': payment.partner_id.id,
                            'line_ids': [
                                # Receivable / Payable / Transfer line.
                                (0, 0, {
                                    'name': rec_pay_line_name,
                                    'amount_currency': counterpart_amount + write_off_amount if currency_id else 0.0,
                                    'currency_id': currency_id,
                                    'debit': balance + write_off_balance > 0.0 and balance + write_off_balance or 0.0,
                                    'credit': balance + write_off_balance < 0.0 and -balance - write_off_balance or 0.0,
                                    'date_maturity': payment.payment_date,
                                    'partner_id': payment.partner_id.id,
                                    'account_id': payment.destination_account_id.id,
                                    'payment_id': payment.id,
                                    'invoice_id': x.invoice_id.id,
                                }),
                                # Liquidity line.
                                (0, 0, {
                                    'name': liquidity_line_name,
                                    'amount_currency': -liquidity_amount if liquidity_line_currency_id else 0.0,
                                    'currency_id': liquidity_line_currency_id,
                                    'debit': round((balance + total_tds_tax_amount),2) < 0.0 and round((-balance +total_tds_tax_amount),2) or 0.0,
                                    'credit': balance > 0.0 and balance or 0.0,
                                    'date_maturity': payment.payment_date,
                                    'partner_id': payment.partner_id.id,
                                    'account_id': liquidity_line_account.id,
                                    'payment_id': payment.id,
                                    'invoice_id': x.invoice_id.id,
                                }),
                            ],
                        }
                    if x.amount_total_tax and x.tax_ids_before:
                        tds_tag = False
                        tag_ids = []
                        for tax in x.tax_ids_before:                            
                            tax_repartition_lines = tax.invoice_repartition_line_ids.filtered(
                                lambda x: x.repartition_type == 'tax')
                            
                            if payment.payment_type == 'outbound' and payment.partner_type == 'supplier':
                                
                                taxes = tax._origin.compute_all(
                                    x.allocation - x.tax_amount)
                                tds_tax_amount = taxes['total_included'] - taxes[
                                    'total_excluded'] if taxes else 0
                                tag_ids = []
                                for tax_rec in taxes.get('taxes'):
                                    if tax._origin.id == tax_rec.get('id'):
                                        tag_ids = (tax_rec.get('tag_ids'))
                                amount_tax = 0             
                                for l in payment.tds_multi_acc_ids:
                                    if l.name == tax.name and l.invoice == x.invoice:
                                        if l.amount < 0:
                                            amount_tax = l.amount * -1
                                        else:
                                            amount = amount

                                move_vals['line_ids'].append((0, 0, {
                                    'name': tax.name,
                                    'amount_currency': tds_tax_amount,
                                    'currency_id': currency_id,
                                    'debit': 0,
                                    'credit': amount_tax,
                                    'date_maturity': payment.payment_date,
                                    'partner_id': payment.partner_id.id,
                                    'tds_tag': True,
                                    'account_id': tax_repartition_lines.id and tax_repartition_lines.account_id.id,
                                    'payment_id': payment.id,
                                    'tax_ids': [(6, 0, tax.ids)],
                                    'tag_ids': [(6, 0, tag_ids)],
                                    'invoice_id': x.invoice_id.id,
                                }))
                            if payment.payment_type == 'inbound' and payment.partner_type == 'customer':
                                
                                taxes = tax._origin.compute_all(
                                    x.allocation - x.tax_amount)
                                tds_tax_amount = taxes['total_included'] - taxes[
                                    'total_excluded'] if taxes else 0
                                tag_ids = []
                                for tax_rec in taxes.get('taxes'):
                                    if tax._origin.id == tax_rec.get('id'):
                                        tag_ids = (tax_rec.get('tag_ids'))
                                amount_tax = 0             
                                for l in payment.tds_multi_acc_ids:
                                    if l.name == tax.name and l.invoice == x.invoice:
                                        if l.amount < 0:
                                            amount_tax = l.amount * -1
                                        else:
                                            amount = amount

                                move_vals['line_ids'].append((0, 0, {
                                    'name': tax.name,
                                    'amount_currency': tds_tax_amount,
                                    'currency_id': currency_id,
                                    'debit': amount_tax,
                                    'credit': 0,
                                    'date_maturity': payment.payment_date,
                                    'partner_id': payment.partner_id.id,
                                    'tds_tag': True,
                                    'account_id': tax_repartition_lines.id and tax_repartition_lines.account_id.id,
                                    'payment_id': payment.id,
                                    'tax_ids': [(6, 0, tax.ids)],
                                    'tag_ids': [(6, 0, tag_ids)],
                                    'invoice_id': x.invoice_id.id,
                                }))

                else:
                    move_vals = {
                        'date': payment.payment_date,
                        'ref': payment.communication,
                        'journal_id': payment.journal_id.id,
                        'currency_id': payment.journal_id.currency_id.id or payment.company_id.currency_id.id,
                        'partner_id': payment.partner_id.id,
                        'line_ids': [
                            # Receivable / Payable / Transfer line.
                            (0, 0, {
                                'name': rec_pay_line_name,
                                'amount_currency': counterpart_amount + write_off_amount if currency_id else 0.0,
                                'currency_id': currency_id,
                                'debit': balance + write_off_balance > 0.0 and balance + write_off_balance or 0.0,
                                'credit': balance + write_off_balance < 0.0 and -balance - write_off_balance or 0.0,
                                'date_maturity': payment.payment_date,
                                'partner_id': payment.partner_id.id,
                                'account_id': payment.destination_account_id.id,
                                'payment_id': payment.id,
                                'invoice_id': x.invoice_id.id,
                            }),
                            # Liquidity line.
                            (0, 0, {
                                'name': liquidity_line_name,
                                'amount_currency': -liquidity_amount if liquidity_line_currency_id else 0.0,
                                'currency_id': liquidity_line_currency_id,
                                'debit': balance < 0.0 and -balance or 0.0,
                                'credit': balance > 0.0 and balance or 0.0,
                                'date_maturity': payment.payment_date,
                                'partner_id': payment.partner_id.id,
                                'account_id': liquidity_line_account.id,
                                'payment_id': payment.id,
                                'invoice_id': x.invoice_id.id,
                            }),
                        ],
                    }
                if write_off_balance:
                    # Write-off line.
                    move_vals['line_ids'].append((0, 0, {
                        'name': payment.writeoff_label,
                        'amount_currency': -write_off_amount,
                        'currency_id': currency_id,
                        'debit': write_off_balance < 0.0 and -write_off_balance or 0.0,
                        'credit': write_off_balance > 0.0 and write_off_balance or 0.0,
                        'date_maturity': payment.payment_date,
                        'partner_id': payment.partner_id.id,
                        'account_id': payment.writeoff_account_id.id,
                        'payment_id': payment.id,
                    }))

                if move_names:
                    move_vals['name'] = move_names[0]

                all_move_vals.append(move_vals)

                # ==== 'transfer' ====
                if payment.payment_type == 'transfer':
                    journal = payment.destination_journal_id

                    # Manage custom currency on journal for liquidity line.
                    if journal.currency_id and payment.currency_id != journal.currency_id:
                        # Custom currency on journal.
                        liquidity_line_currency_id = journal.currency_id.id
                        transfer_amount = company_currency._convert(balance, journal.currency_id, payment.company_id, payment.payment_date)
                    else:
                        # Use the payment currency.
                        liquidity_line_currency_id = currency_id
                        transfer_amount = counterpart_amount

                    transfer_move_vals = {
                        'date': payment.payment_date,
                        'ref': payment.communication,
                        'partner_id': payment.partner_id.id,
                        'journal_id': payment.destination_journal_id.id,
                        'line_ids': [
                            # Transfer debit line.
                            (0, 0, {
                                'name': payment.name,
                                'amount_currency': -counterpart_amount if currency_id else 0.0,
                                'currency_id': currency_id,
                                'debit': balance < 0.0 and -balance or 0.0,
                                'credit': balance > 0.0 and balance or 0.0,
                                'date_maturity': payment.payment_date,
                                'partner_id': payment.partner_id.id,
                                'account_id': payment.company_id.transfer_account_id.id,
                                'payment_id': payment.id,
                            }),
                            # Liquidity credit line.
                            (0, 0, {
                                'name': _('Transfer from %s') % payment.journal_id.name,
                                'amount_currency': transfer_amount if liquidity_line_currency_id else 0.0,
                                'currency_id': liquidity_line_currency_id,
                                'debit': balance > 0.0 and balance or 0.0,
                                'credit': balance < 0.0 and -balance or 0.0,
                                'date_maturity': payment.payment_date,
                                'partner_id': payment.partner_id.id,
                                'account_id': payment.destination_journal_id.default_credit_account_id.id,
                                'payment_id': payment.id,
                            }),
                        ],
                    }

                    if move_names and len(move_names) == 2:
                        transfer_move_vals['name'] = move_names[1]

                    all_move_vals.append(transfer_move_vals)
        return all_move_vals



  




