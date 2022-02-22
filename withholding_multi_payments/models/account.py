from odoo import fields, models, _


class AccountTax(models.Model):
    _inherit = 'account.tax'

    tds = fields.Boolean('TDS', default=False)
    payment_excess = fields.Float('Payment in excess of')
    tds_applicable = fields.Selection([('person', 'Individual'),
                                       ('company', 'Company'),
                                       ('common', 'Common')], string='Applicable to')
