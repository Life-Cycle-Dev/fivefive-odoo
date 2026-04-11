from odoo import fields, models
from odoo.exceptions import UserError


class PurchaseOrderCancelWizard(models.TransientModel):
    _name = "five.five.purchase.order.cancel.wizard"
    _description = "Cancel purchase order with reason"

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        required=True,
        ondelete="cascade",
    )
    reason = fields.Text(string="Reason", required=True)

    def action_confirm_cancel(self):
        self.ensure_one()
        reason = (self.reason or "").strip()
        if not reason:
            raise UserError("กรุณาระบุเหตุผลการยกเลิก")

        po = self.purchase_order_id
        if po.state != "draft":
            raise UserError("สามารถ Cancel PO ที่อยู่ใน status Draft เท่านั้น ไม่สามารถดำเนินการต่อได้")

        po.write({"state": "cancelled", "reason_cancel": reason})
        return {"type": "ir.actions.act_window_close"}
