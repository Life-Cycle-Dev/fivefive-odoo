from datetime import date
from odoo import fields, models


class PurchaseOrderPaymentWizard(models.TransientModel):
    _name = "five.five.purchase.order.payment.wizard"
    _description = "Pay purchase order wizard"

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        required=True,
        ondelete="cascade",
    )

    amount = fields.Float(string="Amount", default=0, required=True)
    pay_at = fields.Date(string="Payment At", required=True, default=date.today())
    attachment = fields.Binary(string="Attachment")
    note = fields.Char(string="Note")

    def action_confirm(self):
        self.ensure_one()

        po = self.purchase_order_id
