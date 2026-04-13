from odoo import fields, models
from odoo.exceptions import UserError


class PurchaseOrderPaymentCancelWizard(models.TransientModel):
    _name = "five.five.purchase.order.payment.cancel.wizard"
    _description = "Cancel purchase order payment with reason wizard"

    payment_id = fields.Many2one(
        "five.five.purchase.order.payment",
        string="Payment",
        required=True,
        ondelete="cascade",
    )
    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        related="payment_id.purchase_order_id",
        store=False,
        readonly=True,
    )
    reason = fields.Text(string="Reason", required=True)
    attachment = fields.Binary(string="Attachment")
    attachment_name = fields.Char(string="Attachment Name")

    def action_confirm_cancel(self):
        self.ensure_one()
        reason = (self.reason or "").strip()
        if not reason:
            raise UserError("กรุณาระบุเหตุผลการยกเลิก Payment")

        self.payment_id.action_cancel_payment(
            reason=reason,
            cancel_attachment=self.attachment,
            cancel_attachment_name=self.attachment_name,
        )
        return {"type": "ir.actions.act_window_close"}
