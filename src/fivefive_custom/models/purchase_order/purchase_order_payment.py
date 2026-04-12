from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class PurchaseOrderPayment(models.Model):
    _name = "five.five.purchase.order.payment"
    _description = "Purchase Order Payment"

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        required=True,
        index=True,
    )

    amount_usd = fields.Float(string="Amount (USD)", default=0, required=True)
    amount_thb = fields.Float(string="Amount (THB)", default=0, required=True)
    pay_at = fields.Date(string="Payment At", required=True)
    attachment = fields.Binary(string="Attachment")
    note = fields.Char(string="Note")

    is_cancel = fields.Boolean(string="Is Cancel?", default=False)
    cancel_reason = fields.Text(string="Cancel Reason")
    cancel_attachment = fields.Binary(string="Cancel Attachment")
    cancel_attachment_name = fields.Char(string="Cancel Attachment Name")
    reversed_from_payment_id = fields.Many2one(
        "five.five.purchase.order.payment",
        string="Reversed From Payment",
        index=True,
    )
    is_reversed = fields.Boolean(
        string="Is Reversed",
        compute="_compute_is_reversed",
    )

    def _compute_is_reversed(self):
        for payment in self:
            payment.is_reversed = bool(self.search_count([("reversed_from_payment_id", "=", payment.id)]))

    def _recompute_purchase_order_payment_summary(self, purchase_orders):
        for po in purchase_orders:
            amount_paid_usd = sum(po.payment_ids.mapped("amount_usd"))
            amount_paid_thb = sum(po.payment_ids.mapped("amount_thb"))
            po.write(
                {
                    "amount_paid_usd": amount_paid_usd,
                    "amount_paid_thb": amount_paid_thb,
                }
            )

    def action_open_cancel_payment_wizard(self):
        self.ensure_one()
        if self.purchase_order_id.state not in ["draft", "po_issued", "documents_completed"]:
            raise UserError(f"ไม่สามารถยกเลิก Payment ที่อยู่ใน status {self.purchase_order_id.state} ได้")
        if self.is_cancel:
            raise UserError("Payment นี้ถูกยกเลิกไปแล้ว")
        if float_compare(self.amount_usd, 0, precision_digits=2) <= 0:
            raise UserError("ยกเลิกได้เฉพาะ Payment ที่มียอดมากกว่า 0")
        if self.is_reversed:
            raise UserError("Payment นี้ถูกยกเลิกไปแล้ว")

        return {
            "type": "ir.actions.act_window",
            "name": "ยกเลิก Payment",
            "res_model": "five.five.purchase.order.payment.cancel.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_payment_id": self.id,
            },
        }

    def action_cancel_payment(self, reason, cancel_attachment=False, cancel_attachment_name=False):
        for payment in self:
            if payment.purchase_order_id.state not in ["draft", "po_issued", "documents_completed"]:
                raise UserError(f"ไม่สามารถยกเลิก Payment ที่อยู่ใน status {self.purchase_order_id.state} ได้")

            if payment.is_cancel:
                raise UserError("Payment นี้ถูกยกเลิกไปแล้ว")

            if float_compare(payment.amount_usd, 0, precision_digits=2) <= 0:
                raise UserError("ยกเลิกได้เฉพาะ Payment ที่มียอดมากกว่า 0")

            existed_reversal = self.search_count([("reversed_from_payment_id", "=", payment.id)])
            if existed_reversal:
                raise UserError("Payment นี้ถูกยกเลิกไปแล้ว")

            reason = (reason or "").strip()
            if not reason:
                raise UserError("กรุณาระบุเหตุผลการยกเลิก Payment")

            self.create(
                {
                    "purchase_order_id": payment.purchase_order_id.id,
                    "pay_at": fields.Date.context_today(self),
                    "amount_usd": -abs(payment.amount_usd),
                    "amount_thb": -abs(payment.amount_thb),
                    "is_cancel": True,
                    "cancel_reason": reason,
                    "cancel_attachment": cancel_attachment,
                    "cancel_attachment_name": cancel_attachment_name,
                    "reversed_from_payment_id": payment.id,
                }
            )
            payment._recompute_purchase_order_payment_summary(payment.purchase_order_id)

        return True
