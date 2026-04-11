from odoo import models, fields

class PurchaseOrderDocument(models.Model):
    _name = "five.five.purchase.order.document"
    _description = "Purchase Order Document"

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        required=True,
        ondelete="cascade",
        index=True,
    )

    type = fields.Selection(
        [
            ("ci", "CI"),
            ("pl", "PL"),
            ("bl", "BL"),
            ("co", "CO"),
            ("hc", "HC"),
            ("other", "Other"),
        ],
        string="Document Type",
        default="other",
        required=True,
        tracking=True,
    )