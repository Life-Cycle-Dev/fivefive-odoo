from datetime import date
from odoo import fields, models
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

    amount_usd = fields.Float(string="Amount (USD)", default=0, required=True)
    amount_thb = fields.Float(string="Amount (THB)", default=0, required=True)
    pay_at = fields.Date(string="Payment At", required=True, default=date.today())
    attachment = fields.Binary(string="Attachment")
    note = fields.Char(string="Note")

    def action_confirm(self):
        self.ensure_one()

        if self.amount_usd <= 0:
            raise UserError("Amount ต้องมากกว่า 0")

        po = self.purchase_order_id
        if po.state not in ["po_issued", "documents_completed", "clearing"]:
            raise UserError("สามารถจ่ายเงินได้เฉพาะ PO ที่อยู่ใน status Issued, Documents Completed, หรือ Clearing เท่านั้น")

        if float_compare(self.amount_usd, po.balance_amount_usd, precision_digits=2) > 0:
            raise UserError("Amount ต้องไม่มากกว่ายอดคงเหลือของ PO")

        payment = self.env["five.five.purchase.order.payment"].create(
            {
                "purchase_order_id": po.id,
                "amount_usd": self.amount_usd,
                "amount_thb": self.amount_thb,
                "pay_at": self.pay_at,
                "attachment": self.attachment,
                "note": self.note,
            }
        )
        payment._recompute_purchase_order_payment_summary(po)

        return {
            "type": "ir.actions.act_window_close"
        }
