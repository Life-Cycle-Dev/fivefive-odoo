from odoo import models, fields
from odoo.exceptions import UserError

class PurchaseOrderDocumentCompleted(models.Model):
    _inherit = "five.five.purchase.order"

    document_ids = fields.One2many(
        "five.five.purchase.order.document",
        "purchase_order_id",
        string="Documents",
        required=True,
        tracking=True,
    )

    def action_post(self):
        for record in self:
            if record.state != "po_issued":
                raise UserError("เฉพาะ PO ที่อยู่ใน status PO Issued เท่านั้น ที่สามารถ Post ได้ ไม่สามารถดำเนินการต่อได้")

            required_types = {"ci", "pl", "bl", "co", "hc"}
            attached_types = set(record.document_ids.mapped("type"))

            if not required_types <= attached_types:
                raise UserError("กรุณาแนบเอกสารที่จำเป็นทั้งหมด (CI, PL, BL, CO, HC) ก่อนทำการ Post PO ใบนี้")

            record.state = "documents_completed"

        return True