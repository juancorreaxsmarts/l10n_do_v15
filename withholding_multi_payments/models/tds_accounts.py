from odoo import api, fields, models, _


class tds_accounts(models.Model):
    _name = 'tds.accounts'

    tds_account_id = fields.Many2one('account.account', string="Difference Account",
                                     domain=[('deprecated', '=', False)], copy=False, required="1")
    name = fields.Char('Description')
    amt_percent = fields.Float(string='Amount(%)', digits=(16, 2))
    amount = fields.Monetary(string='Payment Amount', required=True)
    tax_id = fields.Many2one('account.tax', string='Tax', required=True, )
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.user.company_id.currency_id)
    payment_id = fields.Many2one('account.payment', string='Payment Record')
    invoice_id = fields.Many2one('account.move', string="Invoice")
    invoice = fields.Char(related='invoice_id.name', string="Invoice Number")
    repeat = fields.Boolean(
        string='Repetido',
    )