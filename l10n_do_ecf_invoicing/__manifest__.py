{
    "name": "Dominican Republic EDI Invoicing",
    "summary": """
        Dominican Republic DGII Electronic Invoicing""",
    "author": "Indexa",
    "website": "https://www.indexa.do",
    "category": "Accounting",
    "version": "15.0.1.10.9",
    "depends": ["l10n_do_accounting", "l10n_do_debit_note"],
    "data": [
        "views/account_views.xml",
        "views/res_config_settings_views.xml",
        "data/ir_config_parameter_data.xml",
        "data/ir_cron_data.xml",
        "data/account_journal_data.xml",
    ],
}
