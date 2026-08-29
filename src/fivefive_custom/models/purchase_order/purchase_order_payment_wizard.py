from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class PurchaseOrderPaymentWizard(models.TransientModel):
    _name = "five.five.purchase.order.payment.wizard"
    _description = "Pay purchase order wizard"

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        required=True,
        ondelete="cascade",
    )
    is_thailand_po = fields.Boolean(
        related="purchase_order_id.is_thailand_po",
        readonly=True,
    )

    amount_usd = fields.Float(string="Amount (USD)", default=0, required=True)
    exchange_rate = fields.Float(
        string="Rate (THB/USD)",
        digits=(16, 6),
        default=0.0,
    )
    amount_thb = fields.Float(
        string="Amount (THB)",
        compute="_compute_amount_thb",
        store=True,
        readonly=False,
    )
    pay_at = fields.Date(string="Payment At", required=True, default=date.today())
    payment_status = fields.Selection(
        [
            ("pending", "Pending"),
            ("paid", "Paid"),
        ],
        string="Status",
        default="pending",
        required=True,
    )
    attachment = fields.Binary(string="Attachment")
    note = fields.Char(string="Note")

    @api.depends("amount_usd", "exchange_rate", "is_thailand_po")
    def _compute_amount_thb(self):
        for wizard in self:
            if wizard.is_thailand_po:
                wizard.amount_thb = wizard.amount_usd
            else:
                wizard.amount_thb = (wizard.amount_usd or 0.0) * (wizard.exchange_rate or 0.0)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        po_id = res.get("purchase_order_id") or self.env.context.get("default_purchase_order_id")
        if po_id:
            po = self.env["five.five.purchase.order"].browse(po_id)
            if po.is_thailand_po:
                res["exchange_rate"] = 1.0
            elif po.exchange_rate_thb_per_usd:
                res["exchange_rate"] = po.exchange_rate_thb_per_usd
        default_amount = self.env.context.get("default_amount_usd")
        if default_amount is not None:
            res["amount_usd"] = default_amount
        return res

    @api.onchange("is_thailand_po")
    def _onchange_is_thailand_po(self):
        if self.is_thailand_po:
            self.exchange_rate = 1.0

    def action_confirm(self):
        self.ensure_one()

        if self.amount_usd <= 0:
            raise UserError("Amount ต้องมากกว่า 0")

        if not self.is_thailand_po and (self.exchange_rate or 0.0) <= 0:
            raise UserError("กรุณากรอก Rate (THB/USD)")

        po = self.purchase_order_id
        if po.state not in ["po_issued", "documents_completed", "clearing"]:
            raise UserError("สามารถจ่ายเงินได้เฉพาะ PO ที่อยู่ใน status Issued, Documents Completed, หรือ Clearing เท่านั้น")

        remaining_to_record = po.total_amount_usd - po.amount_recorded_usd
        if float_compare(self.amount_usd, remaining_to_record, precision_digits=2) > 0:
            raise UserError("Amount ต้องไม่มากกว่ายอดที่ยังไม่ได้บันทึก Payment")

        amount_thb = self.amount_usd if po.is_thailand_po else self.amount_usd * self.exchange_rate

        payment = self.env["five.five.purchase.order.payment"].create(
            {
                "purchase_order_id": po.id,
                "amount_usd": self.amount_usd,
                "amount_thb": amount_thb,
                "pay_at": self.pay_at,
                "payment_status": self.payment_status,
                "attachment": self.attachment,
                "note": self.note,
            }
        )
        payment._recompute_purchase_order_payment_summary(po)

        return {
            "type": "ir.actions.act_window_close"
        }
