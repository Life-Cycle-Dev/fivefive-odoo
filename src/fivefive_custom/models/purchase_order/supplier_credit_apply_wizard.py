from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class SupplierCreditApplyWizard(models.TransientModel):
    _name = "five.five.supplier.credit.apply.wizard"
    _description = "Apply supplier credit to purchase order"

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        required=True,
        readonly=True,
    )
    supplier_id = fields.Many2one(
        "five.five.supplier",
        related="purchase_order_id.supplier_id",
        readonly=True,
    )
    available_credit_usd = fields.Float(
        string="Available Credit (USD)",
        digits=(16, 2),
        readonly=True,
    )
    remaining_po_usd = fields.Float(
        string="Remaining PO Amount (USD)",
        digits=(16, 2),
        readonly=True,
    )
    apply_amount_usd = fields.Float(
        string="Apply Amount (USD)",
        digits=(16, 2),
    )
    credit_summary = fields.Text(
        string="Credit Summary",
        readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        po_id = res.get("purchase_order_id") or self.env.context.get("default_purchase_order_id")
        if not po_id:
            return res

        po = self.env["five.five.purchase.order"].browse(po_id)
        res["purchase_order_id"] = po.id
        credits = self.env["five.five.supplier.credit"]._get_available_for_supplier(po.supplier_id)
        available = sum(credits.mapped("remaining_usd"))
        remaining_po = max(po.total_amount_usd - po.amount_recorded_usd, 0.0)
        res["available_credit_usd"] = available
        res["remaining_po_usd"] = remaining_po
        res["apply_amount_usd"] = min(available, remaining_po) if remaining_po else available
        res["credit_summary"] = self._format_credit_summary(credits)
        return res

    @api.model
    def _format_credit_summary(self, credits):
        if not credits:
            return _("No supplier credit available.")
        lines = []
        for credit in credits:
            lines.append(
                _("- %(amount)s USD from %(po)s")
                % {
                    "amount": f"{credit.remaining_usd:,.2f}",
                    "po": credit.source_purchase_order_id.number,
                }
            )
        return "\n".join(lines)

    def action_confirm(self):
        self.ensure_one()
        po = self.purchase_order_id
        if not po:
            raise UserError(_("Purchase Order not found."))
        if po.state not in ("draft", "po_issued"):
            raise UserError(_("Supplier credit can only be applied on draft or issued POs."))
        if po.payment_ids.filtered("supplier_credit_id"):
            raise UserError(_("Supplier credit has already been applied to this PO."))

        apply_amount = self.apply_amount_usd or 0.0
        if float_compare(apply_amount, 0, precision_digits=2) <= 0:
            raise UserError(_("Apply amount must be greater than zero."))

        remaining_po = po.total_amount_usd - po.amount_recorded_usd
        if float_compare(apply_amount, remaining_po, precision_digits=2) > 0:
            raise UserError(_("Apply amount cannot exceed the remaining PO amount."))
        if float_compare(apply_amount, self.available_credit_usd, precision_digits=2) > 0:
            raise UserError(_("Apply amount exceeds available supplier credit."))

        po._apply_supplier_credits(apply_amount)
        return {"type": "ir.actions.act_window_close"}

    def action_skip(self):
        self.ensure_one()
        if self.purchase_order_id:
            self.purchase_order_id.supplier_credit_wizard_skipped = True
        return {"type": "ir.actions.act_window_close"}
