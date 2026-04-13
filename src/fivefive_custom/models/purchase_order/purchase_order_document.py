from odoo import _, api, fields, models
from odoo.exceptions import UserError

_ALLOWED_PO_STATES_FOR_DOCUMENTS = ("draft", "po_issued")


class PurchaseOrderDocument(models.Model):
    _name = "five.five.purchase.order.document"
    _description = "Purchase Order Document"

    number = fields.Char(string="Document Number")
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
            ("do", "DO"),
            ("other", "Other"),
        ],
        string="Document Type",
        default="other",
        required=True,
        tracking=True,
    )

    attachment_file = fields.Binary(string="File", attachment=True, required=True)
    attachment_name = fields.Char(string="File Name", required=True)

    @api.model
    def _ff_po_states_allow_document_mutation(self, purchase_orders):
        if self.env.context.get("skip_po_document_state_check"):
            return

        invalid = purchase_orders.filtered(
            lambda p: p and p.state not in _ALLOWED_PO_STATES_FOR_DOCUMENTS
        )
        if invalid:
            raise UserError(
                "แก้ไข/เพิ่ม/ลบเอกสารแนบได้เฉพาะเมื่อ PO อยู่ใน Draft หรือ PO Issued เท่านั้น"
            )

    @api.model_create_multi
    def create(self, vals_list):
        po_ids = [v["purchase_order_id"] for v in vals_list if v.get("purchase_order_id")]
        if po_ids:
            self._ff_po_states_allow_document_mutation(
                self.env["five.five.purchase.order"].browse(po_ids)
            )
        return super().create(vals_list)

    def write(self, vals):
        orders = self.mapped("purchase_order_id")
        if vals.get("purchase_order_id"):
            orders |= self.env["five.five.purchase.order"].browse(vals["purchase_order_id"])
        self._ff_po_states_allow_document_mutation(orders)
        return super().write(vals)

    def unlink(self):
        self._ff_po_states_allow_document_mutation(self.mapped("purchase_order_id"))
        return super().unlink()

    def action_open_upload_wizard(self):
        self.ensure_one()
        rid = self._ids[0] if self._ids else 0

        if not isinstance(rid, int) or rid <= 0:
            raise UserError("กรุณาบันทึกข้อมูล PO ก่อนทำการอัพเดทเอกสารเพิ่มเติม")

        return {
            "type": "ir.actions.act_window",
            "name": _("Upload File"),
            "res_model": "five.five.purchase.order.document.upload.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_document_id": self.id},
        }

    def action_download_document_file(self):
        self.ensure_one()
        attachment = self.env["ir.attachment"].search(
            [
                ("res_model", "=", self._name),
                ("res_id", "=", self.id),
                ("res_field", "=", "attachment_file"),
            ],
            limit=1,
        )

        if not attachment:
            raise UserError("ไม่พบไฟล์ที่อัพโหลด")

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }
