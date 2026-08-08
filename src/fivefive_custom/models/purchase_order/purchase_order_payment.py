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
    supplier_credit_id = fields.Many2one(
        "five.five.supplier.credit",
        string="Supplier Credit",
        ondelete="set null",
        index=True,
        readonly=True,
    )

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

    def init(self):
        super().init()
        self.env.cr.execute(
            """
            UPDATE five_five_purchase_order_payment
               SET payment_status = 'paid'
             WHERE payment_status IS NULL
                OR payment_status = ''
            """
        )
        self.env.cr.execute(
            """
            UPDATE five_five_purchase_order po
               SET amount_recorded_usd = COALESCE(sub.usd, 0),
                   amount_recorded_thb = COALESCE(sub.thb, 0),
                   amount_paid_usd = COALESCE(sub.paid_usd, 0),
                   amount_paid_thb = COALESCE(sub.paid_thb, 0)
              FROM (
                    SELECT purchase_order_id,
                           SUM(amount_usd) AS usd,
                           SUM(amount_thb) AS thb,
                           SUM(CASE WHEN payment_status = 'paid' THEN amount_usd ELSE 0 END) AS paid_usd,
                           SUM(CASE WHEN payment_status = 'paid' THEN amount_thb ELSE 0 END) AS paid_thb
                      FROM five_five_purchase_order_payment
                  GROUP BY purchase_order_id
                   ) sub
             WHERE po.id = sub.purchase_order_id
            """
        )

    def _compute_is_reversed(self):
        for payment in self:
            payment.is_reversed = bool(self.search_count([("reversed_from_payment_id", "=", payment.id)]))

    def _recompute_purchase_order_payment_summary(self, purchase_orders):
        for po in purchase_orders:
            amount_recorded_usd = sum(po.payment_ids.mapped("amount_usd"))
            amount_recorded_thb = sum(po.payment_ids.mapped("amount_thb"))
            paid_payments = po.payment_ids.filtered(lambda payment: payment.payment_status == "paid")
            amount_paid_usd = sum(paid_payments.mapped("amount_usd"))
            amount_paid_thb = sum(paid_payments.mapped("amount_thb"))
            po.write(
                {
                    "amount_recorded_usd": amount_recorded_usd,
                    "amount_recorded_thb": amount_recorded_thb,
                    "amount_paid_usd": amount_paid_usd,
                    "amount_paid_thb": amount_paid_thb,
                }
            )
            po.commercial_invoice_line_ids._ff_recompute_auto_fixed_costs_for_converts()

    def action_mark_as_paid(self):
        for payment in self:
            if payment.purchase_order_id.state not in ["po_issued", "documents_completed", "clearing", "closed"]:
                raise UserError("ไม่สามารถ Mark as Paid ใน status นี้ได้")
            if payment.is_cancel:
                raise UserError("Payment ที่ถูกยกเลิกแล้วไม่สามารถ Mark as Paid ได้")
            if payment.is_reversed:
                raise UserError("Payment นี้ถูกยกเลิกไปแล้ว")
            if payment.payment_status == "paid":
                raise UserError("Payment นี้ถูก Mark as Paid แล้ว")
            if float_compare(payment.amount_usd, 0, precision_digits=2) <= 0:
                raise UserError("Mark as Paid ได้เฉพาะ Payment ที่มียอดมากกว่า 0")
            payment.payment_status = "paid"
            payment._recompute_purchase_order_payment_summary(payment.purchase_order_id)
        return True

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
                raise UserError(f"ไม่สามารถยกเลิก Payment ที่อยู่ใน status {payment.purchase_order_id.state} ได้")

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
                    "payment_status": payment.payment_status,
                    "is_cancel": True,
                    "cancel_reason": reason,
                    "cancel_attachment": cancel_attachment,
                    "cancel_attachment_name": cancel_attachment_name,
                    "reversed_from_payment_id": payment.id,
                }
            )
            payment._recompute_purchase_order_payment_summary(payment.purchase_order_id)

        return True
