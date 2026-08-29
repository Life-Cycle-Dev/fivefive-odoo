from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class SupplierCreditManualWizard(models.TransientModel):
    _name = "five.five.supplier.credit.manual.wizard"
    _description = "Create manual supplier credit"

    supplier_id = fields.Many2one(
        "five.five.supplier",
        string="Supplier",
        required=True,
        readonly=True,
    )
    amount_usd = fields.Float(string="Credit (USD)", digits=(16, 2), required=True)
    amount_thb = fields.Float(string="Credit (THB)", digits=(16, 2), required=True)
    note = fields.Char(string="Note")

    def action_confirm(self):
        self.ensure_one()
        if float_compare(self.amount_usd, 0, precision_digits=2) <= 0:
            raise UserError(_("Credit amount must be greater than zero."))
        if float_compare(self.amount_thb, 0, precision_digits=2) <= 0:
            raise UserError(_("Credit amount (THB) must be greater than zero."))

        self.env["five.five.supplier.credit"].create(
            {
                "supplier_id": self.supplier_id.id,
                "is_manual": True,
                "amount_usd": self.amount_usd,
                "amount_thb": self.amount_thb,
                "remaining_usd": self.amount_usd,
                "remaining_thb": self.amount_thb,
                "note": self.note,
            }
        )
        return {"type": "ir.actions.act_window_close"}
