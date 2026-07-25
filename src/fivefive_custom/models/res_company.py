from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    pos_vat_included = fields.Boolean(
        string="POS VAT Included",
        default=False,
        help="Default for new stores: prices include VAT and receipt shows abbreviated tax invoice.",
    )
    pos_vat_percent = fields.Float(
        string="POS VAT %",
        default=7.0,
        help="Default VAT rate for POS receipts on new stores.",
    )
