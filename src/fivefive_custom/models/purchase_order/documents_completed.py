from odoo import models, fields
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

class PurchaseOrderDocumentCompleted(models.Model):
    _inherit = "five.five.purchase.order"

    warehouse_id = fields.Many2one(
        "five.five.warehouse",
        string="Warehouse",
        tracking=True,
    )
    lot_number = fields.Char(
        string="Lot Number",
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

    shipment_container_number = fields.Char(string="Container NO.")
    bl_number = fields.Char(string="BL Number")
    arrived_at = fields.Date(string="Arrived at (eta)")
    ci_number = fields.Char(string="CI Number")

    payment_ids = fields.One2many(
        "five.five.purchase.order.payment",
        "purchase_order_id",
        string="Payments",
        tracking=True,
    )

    def _ff_is_thailand_country(self):
        thailand = self.env.ref("base.th", raise_if_not_found=False)
        return bool(thailand and self.country_id == thailand)

    def action_post(self):
        for record in self:
            error_message = ""
            if record.state != "po_issued":
                raise UserError("เฉพาะ PO ที่อยู่ใน status PO Issued เท่านั้น ที่สามารถ Post ได้ ไม่สามารถดำเนินการต่อได้")

            if record._ff_is_thailand_country():
                if "ci" not in record.document_ids.mapped("type"):
                    error_message += "- กรุณาแนบเอกสาร CI ก่อนทำการ Post PO ใบนี้\n"
            else:
                if record.shipment_container_number == "" or not record.shipment_container_number:
                    error_message += "- กรุณาใส่ Container NO. ก่อน Post PO\n"

                if record.bl_number == "" or not record.bl_number:
                    error_message += "- กรุณาใส่ BL NO. ก่อน Post PO\n"

                if record.arrived_at == "" or not record.arrived_at:
                    error_message += "- กรุณาใส่ Arrived at (eta) ก่อน Post PO\n"

                required_types = ["ci", "pl", "bl", "co", "hc"]
                attached_types = record.document_ids.mapped("type")
                missing_types = [
                    required_type for required_type in required_types if required_type not in attached_types
                ]

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
        default_amount_usd = max(self.total_amount_usd - self.amount_recorded_usd, 0.0)

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

        if float_compare(self.amount_recorded_usd, self.total_amount_usd, precision_digits=2) != 0:
            raise UserError(
                "ต้องบันทึก Payment ให้ครบยอดรวม Commercial Invoice ก่อน Clearing "
                "(สามารถเป็น Pending ได้ ไม่จำเป็นต้อง Mark as Paid)"
            )

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

    def action_cancel_clearing(self):
        self.ensure_one()
        if self.state != "clearing":
            raise UserError("สามารถ Cancel Clearing ได้เฉพาะ PO ที่อยู่ใน status Clearing เท่านั้น")

        return {
            "type": "ir.actions.act_window",
            "name": "ยืนยันยกเลิก Clearing",
            "res_model": "five.five.purchase.order.cancel.clearing.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_purchase_order_id": self.id,
            },
        }

    def action_close(self):
        self.ensure_one()

        if self.state != "clearing":
            raise UserError("สามารถ Close PO ที่อยู่ใน status Clearing เท่านั้น ไม่สามารถดำเนินการต่อได้")

        if not self.warehouse_id:
            raise UserError("กรุณาระบุ Warehouse ก่อนทำการ Close PO")

        if not self.converted_product_ids:
            raise UserError("กรุณา Convert Product ก่อนทำการ Close PO")

        return {
            "type": "ir.actions.act_window",
            "name": "Close PO",
            "res_model": "five.five.purchase.order.close.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_purchase_order_id": self.id,
            },
        }
