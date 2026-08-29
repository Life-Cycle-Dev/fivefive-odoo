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
        ondelete="cascade",
        index=True,
    )
    is_manual = fields.Boolean(string="Manual Credit", default=False, index=True)
    amount_usd = fields.Float(string="Credit (USD)", digits=(16, 2), required=True)
    amount_thb = fields.Float(string="Credit (THB)", digits=(16, 2), required=True)
    remaining_usd = fields.Float(string="Remaining (USD)", digits=(16, 2), required=True)
    remaining_thb = fields.Float(string="Remaining (THB)", digits=(16, 2), required=True)
    active = fields.Boolean(default=True)
    note = fields.Char(string="Note")
    source_display = fields.Char(
        string="Source",
        compute="_compute_source_display",
    )

    @api.depends("is_manual", "note", "source_purchase_order_id.number")
    def _compute_source_display(self):
        for credit in self:
            credit.source_display = credit._get_source_label()

    @api.constrains("is_manual", "source_purchase_order_id")
    def _check_source_po(self):
        for credit in self:
            if not credit.is_manual and not credit.source_purchase_order_id:
                raise UserError(_("Source PO is required for non-manual supplier credits."))

    @api.model
    def _get_available_for_supplier(self, supplier, use_thb=False):
        if not supplier:
            return self.browse()
        remaining_field = "remaining_thb" if use_thb else "remaining_usd"
        return self.search(
            [
                ("supplier_id", "=", supplier.id),
                ("active", "=", True),
                (remaining_field, ">", 0),
            ],
            order="id asc",
        )

    @api.model
    def _get_available_amount(self, supplier, use_thb=False):
        credits = self._get_available_for_supplier(supplier, use_thb=use_thb)
        field = "remaining_thb" if use_thb else "remaining_usd"
        return sum(credits.mapped(field))

    @api.model
    def _get_available_amount_usd(self, supplier):
        return self._get_available_amount(supplier, use_thb=False)

    def _get_source_label(self):
        self.ensure_one()
        if self.is_manual:
            return self.note or _("Manual Credit")
        if self.source_purchase_order_id:
            return self.source_purchase_order_id.number
        return _("Unknown")

    def _consume(self, amount_usd):
        self.ensure_one()
        if float_compare(amount_usd, 0, precision_digits=2) <= 0:
            return 0.0, 0.0
        if float_compare(amount_usd, self.remaining_usd, precision_digits=2) > 0:
            raise UserError(_("Applied credit exceeds remaining credit for %s.") % self._get_source_label())

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

    def _consume_thb(self, amount_thb):
        self.ensure_one()
        if float_compare(amount_thb, 0, precision_digits=2) <= 0:
            return 0.0, 0.0
        if float_compare(amount_thb, self.remaining_thb, precision_digits=2) > 0:
            raise UserError(_("Applied credit exceeds remaining credit for %s.") % self._get_source_label())

        ratio = amount_thb / self.remaining_thb if self.remaining_thb else 0.0
        amount_usd = self.remaining_usd * ratio
        self.write(
            {
                "remaining_usd": self.remaining_usd - amount_usd,
                "remaining_thb": self.remaining_thb - amount_thb,
            }
        )
        if float_is_zero(self.remaining_thb, precision_digits=2):
            self.active = False
        return amount_usd, amount_thb
