from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _default_country_id(env):
    return env.ref("base.th", raise_if_not_found=False).id


class Supplier(models.Model):
    _name = "five.five.supplier"
    _description = "Supplier"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Name", required=True, tracking=True)
    contact = fields.Char(string="Contact", required=True, tracking=True)
    tax_id = fields.Char(string="Tax ID", tracking=True)
    country_id = fields.Many2one(
        "res.country",
        string="Country",
        default=lambda self: _default_country_id(self.env),
        tracking=True,
    )
    image = fields.Image(string="Image", max_width=1920, max_height=1920)

    phone = fields.Char(string="Phone", tracking=True)

    account_name = fields.Char(string="Account Name", required=True, tracking=True)
    account_number = fields.Char(string="Account Number", required=True, tracking=True)
    account_bank_name = fields.Char(string="Bank Name", tracking=True)
    account_bank_address = fields.Char(string="Bank Address", tracking=True)
    account_bank_swift_code = fields.Char(string="Bank Swift Code", tracking=True)

    active = fields.Boolean(string="Active", default=True, tracking=True)

    credit_ids = fields.One2many(
        "five.five.supplier.credit",
        "supplier_id",
        string="Credits",
    )
    credit_balance_usd = fields.Float(
        string="Available Credit (USD)",
        compute="_compute_credit_balance",
        digits=(16, 2),
    )
    credit_balance_thb = fields.Float(
        string="Available Credit (THB)",
        compute="_compute_credit_balance",
        digits=(16, 2),
    )

    @api.depends("credit_ids.remaining_usd", "credit_ids.remaining_thb", "credit_ids.active")
    def _compute_credit_balance(self):
        for supplier in self:
            active_credits = supplier.credit_ids.filtered(
                lambda credit: credit.active and credit.remaining_usd > 0
            )
            supplier.credit_balance_usd = sum(active_credits.mapped("remaining_usd"))
            supplier.credit_balance_thb = sum(active_credits.mapped("remaining_thb"))

    @api.constrains("tax_id")
    def _check_tax_id_unique(self):
        for record in self:
            if not record.tax_id:
                continue
            duplicate = self.search_count(
                [
                    ("tax_id", "=", record.tax_id),
                    ("id", "!=", record.id),
                ]
            )
            if duplicate:
                raise ValidationError(
                    _("Tax ID must be unique. The value \"%s\" is already used.")
                    % record.tax_id
                )
