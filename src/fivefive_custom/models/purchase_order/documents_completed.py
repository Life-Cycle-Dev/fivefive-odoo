from odoo import models, fields

class PurchaseOrderDocumentCompleted(models.Model):
    _inherit = "five.five.purchase.order"

    document_ids = fields.One2many(
        "five.five.purchase.order.document",
        "purchase_order_id",
        string="Documents",
    )