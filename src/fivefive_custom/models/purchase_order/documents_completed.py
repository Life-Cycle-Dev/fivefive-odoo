from odoo import models, fields
from odoo.exceptions import UserError

class PurchaseOrderDocumentCompleted(models.Model):
    _inherit = "five.five.purchase.order"

    warehouse_id = fields.Many2one(
        "five.five.warehouse",
        string="Warehouse",
        tracking=True,
    )

    logistic_id = fields.Many2one(
        "five.five.logistic",
        string="Logistic",
        tracking=True,
    )

    document_ids = fields.One2many(
        "five.five.purchase.order.document",
        "purchase_order_id",
        string="Documents",
        tracking=True,
    )

    shipment_container_no = fields.Char(string="Container NO.")
    bl_no = fields.Char(string="BL NO.")
    arrived_at = fields.Date(string="Arrived at (eta)")

    payment_ids = fields.One2many(
        "five.five.purchase.order.payment",
        "purchase_order_id",
        string="Payments",
        tracking=True,
    )

    def action_post(self):
        for record in self:
            error_message = ""
            if record.state != "po_issued":
                raise UserError("เฉพาะ PO ที่อยู่ใน status PO Issued เท่านั้น ที่สามารถ Post ได้ ไม่สามารถดำเนินการต่อได้")

            if record.shipment_container_no == "" or not record.shipment_container_no:
                error_message += "- กรุณาใส่ Container NO. ก่อน Post PO\n"

            if record.bl_no == "" or not record.bl_no:
                error_message += "- กรุณาใส่ BL NO. ก่อน Post PO\n"

            if record.arrived_at == "" or not record.arrived_at:
                error_message += "- กรุณาใส่ Arrived at (eta) ก่อน Post PO\n"

            required_types = ["ci", "pl", "bl", "co", "hc"]
            attached_types = record.document_ids.mapped("type")
            missing_types = [required_type for required_type in required_types if required_type not in attached_types]

            if missing_types:
                error_message += f"- กรุณาแนบเอกสาร {', '.join([required_type.upper() for required_type in missing_types])} ก่อนทำการ Post PO ใบนี้\n"

            if error_message:
                raise UserError("ไม่สามารถ Post PO ได้เนื่องจาก:\n" + error_message)

            record.state = "documents_completed"

        return True

    def action_reset_to_draft(self):
        for record in self:
            if record.state not in ["documents_completed", "po_issued"]:
                raise UserError("สามารถ Reset PO ที่อยู่ใน status Documents Completed หรือ PO Issued เท่านั้น ไม่สามารถดำเนินการต่อได้")

            record.state = "draft"

        return True

    def action_pay(self):
        self.ensure_one()
        default_amount_usd = 0.0
        if self.state in ["documents_completed", "clearing"]:
            default_amount_usd = self.balance_amount_usd

        return {
            "type": "ir.actions.act_window",
            "name": "ทำเรื่องการจ่ายเงิน PO",
            "res_model": "five.five.purchase.order.payment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_purchase_order_id": self.id,
                "default_amount_usd": default_amount_usd,
            },
        }

    def action_clearing(self):
        self.ensure_one()

        if self.state != "documents_completed":
            raise UserError("สามารถ Clearing PO ที่อยู่ใน status Documents Completed เท่านั้น ไม่สามารถดำเนินการต่อได้")

        if self.balance_amount_usd != 0:
            raise UserError("สามารถ Clearing PO ที่มียอดคงเหลือเป็น 0 เท่านั้น ไม่สามารถดำเนินการต่อได้")

        return {
            "type": "ir.actions.act_window",
            "name": "Clearing PO",
            "res_model": "five.five.purchase.order.clearing.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_purchase_order_id": self.id,
                "default_warehouse_id": self.warehouse_id.id,
                "default_logistic_id": self.logistic_id.id,
            },
        }
