# -*- coding: utf-8 -*-

from odoo import models, fields, api


class IrSequence(models.Model):

    _inherit = 'ir.sequence'

    l10n_latam_journal_id = fields.Many2one('account.journal', 'Journal')
    l10n_latam_document_type_id = fields.Many2one('l10n_latam.document.type', 'Document Type')
