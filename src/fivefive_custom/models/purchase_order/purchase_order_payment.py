from odoo import fields, models


class PurchaseOrderPayment(models.Model):
    _name = "five.five.purchase.order.payment"
    _description = "Purchase Order Payment"

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        required=True,
        index=True,
    )

    amount = fields.Float(string="Amount", required=True)
    pay_at = fields.Date(string="Payment At", required=True)
    attachment = fields.Binary(string="Attachment")
    note = fields.Char(string="Note")
