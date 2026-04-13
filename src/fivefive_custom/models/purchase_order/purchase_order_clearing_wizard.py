from odoo import fields, models
from odoo.exceptions import UserError


class PurchaseOrderClearingWizard(models.TransientModel):
    _name = "five.five.purchase.order.clearing.wizard"
    _description = "Purchase order clearing wizard"

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        store=False,
        readonly=True,
    )

    warehouse_id = fields.Many2one(
        "five.five.warehouse",
        string="Warehouse",
        required=True,
    )

    logistic_id = fields.Many2one(
        "five.five.logistic",
        string="Logistic",
        required=True,
    )

    do_attachment = fields.Binary(string="DO Document")
    do_attachment_number = fields.Char(string="DO NO.")
    do_attachment_name = fields.Char(string="DO Document Name")

    def action_confirm(self):
        self.ensure_one()

        if not self.purchase_order_id:
            raise UserError("ไม่พบข้อมูล Purchase Order สำหรับการ Clearing")

        if self.purchase_order_id.state != "documents_completed":
            raise UserError("สามารถ Clearing PO ที่อยู่ใน status Documents Completed เท่านั้น ไม่สามารถดำเนินการต่อได้")

        if self.purchase_order_id.balance_amount_usd != 0:
            raise UserError("สามารถ Clearing PO ที่มียอดคงเหลือเป็น 0 เท่านั้น ไม่สามารถดำเนินการต่อได้")

        if not self.do_attachment:
            raise UserError("กรุณาอัปโหลดเอกสาร DO ก่อนยืนยัน")

        attachment_name = self.do_attachment_name or "do_document"

        self.purchase_order_id.write(
            {
                "warehouse_id": self.warehouse_id.id,
                "logistic_id": self.logistic_id.id,
            }
        )

        self.env["five.five.purchase.order.document"].with_context(
            skip_po_document_state_check=True
        ).create(
            {
                "purchase_order_id": self.purchase_order_id.id,
                "type": "do",
                "number": self.do_attachment_number,
                "attachment_file": self.do_attachment,
                "attachment_name": attachment_name,
            }
        )

        self.purchase_order_id.state = "clearing"

        return {"type": "ir.actions.act_window_close"}
