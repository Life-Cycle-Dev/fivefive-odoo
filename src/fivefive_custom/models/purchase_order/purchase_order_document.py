from odoo import _, fields, models
from odoo.exceptions import UserError


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

    attachment_file = fields.Binary(string="File", attachment=True, required=True)
    attachment_name = fields.Char(string="File Name", required=True)

    def action_open_upload_wizard(self):
        self.ensure_one()
        rid = self._ids[0] if self._ids else 0
        if not isinstance(rid, int) or rid <= 0:
            raise UserError(
                _("Please save the purchase order (or this document line) before using Upload.")
            )
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
            raise UserError(_("No file to download."))
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }