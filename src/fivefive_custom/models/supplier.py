from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Supplier(models.Model):
    _name = "five.five.supplier"
    _description = "Supplier"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Name", required=True, tracking=True)
    contact = fields.Char(string="Contact", required=True, tracking=True)
    tax_id = fields.Char(string="Tax ID", tracking=True)

    phone = fields.Char(string="Phone", tracking=True)

    account_name = fields.Char(string="Account Name", required=True, tracking=True)
    account_number = fields.Char(string="Account Number", required=True, tracking=True)
    account_bank_name = fields.Char(string="Bank Name", tracking=True)
    account_bank_address = fields.Char(string="Bank Address", tracking=True)
    account_bank_swift_code = fields.Char(string="Bank Swift Code", tracking=True)

    active = fields.Boolean(string="Active", default=True, tracking=True)

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
