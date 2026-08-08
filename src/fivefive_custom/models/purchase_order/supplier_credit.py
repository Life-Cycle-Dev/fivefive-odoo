from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class SupplierCredit(models.Model):
    _name = "five.five.supplier.credit"
    _description = "Supplier credit from closed purchase orders"
    _order = "id asc"

    supplier_id = fields.Many2one(
        "five.five.supplier",
        string="Supplier",
        required=True,
        ondelete="cascade",
        index=True,
    )
    source_purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Source PO",
        required=True,
        ondelete="cascade",
        index=True,
    )
    amount_usd = fields.Float(string="Credit (USD)", digits=(16, 2), required=True)
    amount_thb = fields.Float(string="Credit (THB)", digits=(16, 2), required=True)
    remaining_usd = fields.Float(string="Remaining (USD)", digits=(16, 2), required=True)
    remaining_thb = fields.Float(string="Remaining (THB)", digits=(16, 2), required=True)
    active = fields.Boolean(default=True)

    @api.model
    def _get_available_for_supplier(self, supplier):
        if not supplier:
            return self.browse()
        return self.search(
            [
                ("supplier_id", "=", supplier.id),
                ("active", "=", True),
                ("remaining_usd", ">", 0),
            ],
            order="id asc",
        )

    @api.model
    def _get_available_amount_usd(self, supplier):
        credits = self._get_available_for_supplier(supplier)
        return sum(credits.mapped("remaining_usd"))

    def _consume(self, amount_usd):
        self.ensure_one()
        if float_compare(amount_usd, 0, precision_digits=2) <= 0:
            return 0.0, 0.0
        if float_compare(amount_usd, self.remaining_usd, precision_digits=2) > 0:
            raise UserError(_("Applied credit exceeds remaining credit for PO %s.") % self.source_purchase_order_id.number)

        ratio = amount_usd / self.remaining_usd if self.remaining_usd else 0.0
        amount_thb = self.remaining_thb * ratio
        self.write(
            {
                "remaining_usd": self.remaining_usd - amount_usd,
                "remaining_thb": self.remaining_thb - amount_thb,
            }
        )
        if float_is_zero(self.remaining_usd, precision_digits=2):
            self.active = False
        return amount_usd, amount_thb
