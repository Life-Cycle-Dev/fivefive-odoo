from odoo import _, fields, models
from odoo.exceptions import UserError


class PurchaseOrderDocumentUploadWizard(models.TransientModel):
    _name = "five.five.purchase.order.document.upload.wizard"
    _description = "Upload purchase order document file wizard"

    document_id = fields.Many2one(
        "five.five.purchase.order.document",
        string="Document",
        required=True,
        ondelete="cascade",
    )
    upload_file = fields.Binary(string="File")
    upload_filename = fields.Char(string="File Name")

    def action_apply_upload(self):
        self.ensure_one()
        if not self.upload_file:
            raise UserError("กรุณาเลือกไฟล์ที่ต้องการอัพโหลด")
        filename = (self.upload_filename or "").strip() or _("document")
        self.document_id.write(
            {
                "attachment_file": self.upload_file,
                "attachment_name": filename,
            }
        )
        return {"type": "ir.actions.act_window_close"}
