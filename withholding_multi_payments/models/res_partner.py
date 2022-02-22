from odoo import fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    tds_threshold_check = fields.Boolean(string='Check TDS Threshold', default=True)
