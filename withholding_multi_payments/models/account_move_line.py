from odoo import api, fields, models, _


class AccountMoveline(models.Model):
    _inherit = "account.move.line"

    tds_tag = fields.Boolean("TDS Tag", default=False)
    tax_id = fields.Many2one('account.tax', string='Tax', )
    invoice_id = fields.Many2one('account.move', string="Invoice")
