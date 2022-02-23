# -*- coding: utf-8 -*-

from odoo import models, fields, api


class IrSequence(models.Model):

    _inherit = 'ir.sequence'

    l10n_latam_journal_id = fields.Many2one('account.journal', 'Journal')
    l10n_latam_document_type_id = fields.Many2one('l10n_latam.document.type', 'Document Type')

class AccountJournal(models.Model):

    _inherit = "account.journal"

    l10n_latam_country_code = fields.Char(related='company_id.country_id.code', help='Technical field used to hide/show fields regarding the localization')


class AccountMovee(models.Model):

    _inherit = "account.move"

    l10n_latam_country_code = fields.Char(related='company_id.country_id.code', help='Technical field used to hide/show fields regarding the localization')
