# -*- coding: utf-8 -*-

from odoo import models, fields, api


class IrSequence(models.Model):

    _inherit = 'ir.sequence'

    l10n_latam_journal_id = fields.Many2one('account.journal', 'Journal')
    l10n_latam_document_type_id = fields.Many2one('l10n_latam.document.type', 'Document Type')

class AccoMoveLine(models.Model):

    _inherit = 'account.move.line'

    always_set_currency_id = fields.Many2one('res.currency', string='Foreign Currency',
        compute='_compute_always_set_currency_id',
        help="Technical field used to compute the monetary field. As currency_id is not a required field, we need to use either the foreign currency, either the company one.")

    @api.depends('currency_id')
    def _compute_always_set_currency_id(self):
        for line in self:
            line.always_set_currency_id = line.currency_id or line.company_currency_id
