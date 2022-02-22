from odoo import api, fields, models, _



class AccountMove(models.Model):
    _inherit = "account.move"

    @api.depends(
        'line_ids.debit',
        'line_ids.credit',
        'line_ids.currency_id',
        'line_ids.amount_currency',
        'line_ids.amount_residual',
        'line_ids.amount_residual_currency',
        'line_ids.payment_id.state', 'tds_tax_ids')
    def _compute_amount(self):
        super(AccountMove, self)._compute_amount()
        for move in self:
            if move.tds:
                move.total_gross = move.amount_untaxed + move.amount_tax
                total_tds_tax_amount = 0.0
                for tax in move.tds_tax_ids:
                    applicable = True
                    if move.partner_id and move.partner_id.tds_threshold_check and tax:
                        applicable = move.check_turnover(move.partner_id.id, tax.payment_excess,
                                                         move.total_gross)
                    if not applicable or not tax.tds:
                        continue
                    taxes = tax._origin.compute_all(
                        move.total_gross)
                    total_tds_tax_amount += taxes['total_included'] - taxes[
                        'total_excluded'] if taxes else move.total_gross * (tax.amount / 100)
                move.tds_amt = -total_tds_tax_amount
                move.amount_total = move.amount_untaxed + move.amount_tax + move.tds_amt

            else:
                move.total_gross = move.amount_untaxed + move.amount_tax
                move.tds_amt = 0.0
                move.amount_total = move.amount_untaxed + move.amount_tax + move.tds_amt
                move.tds_tax_ids = False

    tds = fields.Boolean('Apply TDS', default=False,
                         states={'draft': [('readonly', False)]})
    tds_tax_ids = fields.Many2many('account.tax', string='TDS',
                                   states={'draft': [('readonly', False)]})
    tds_amt = fields.Monetary(string='TDS Amount',
                              readonly=True, compute='_compute_amount')
    total_gross = fields.Monetary(string='Total',
                                  store=True, readonly=True, compute='_compute_amount')
    amount_total = fields.Monetary(string='Net Total',
                                   store=True, readonly=True, compute='_compute_amount')
    vendor_type = fields.Selection(related='partner_id.company_type', string='Partner Type')
    display_in_report = fields.Boolean('Display TDS in Report', default=False)
