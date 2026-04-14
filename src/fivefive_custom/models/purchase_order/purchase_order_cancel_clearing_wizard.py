from odoo import fields, models
from odoo.exceptions import UserError


class PurchaseOrderCancelClearingWizard(models.TransientModel):
    _name = "five.five.purchase.order.cancel.clearing.wizard"
    _description = "Cancel purchase order clearing"

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        required=True,
        ondelete="cascade",
        readonly=True,
    )
    do_document_count = fields.Integer(
        string="DO Documents",
        compute="_compute_do_document_info",
        readonly=True,
    )
    do_document_numbers = fields.Text(
        string="DO Numbers",
        compute="_compute_do_document_info",
        readonly=True,
    )

    def _compute_do_document_info(self):
        for wizard in self:
            do_docs = wizard.purchase_order_id.document_ids.filtered(lambda doc: doc.type == "do")
            wizard.do_document_count = len(do_docs)
            wizard.do_document_numbers = "\n".join(doc.number for doc in do_docs if doc.number) or "-"

    def action_confirm_cancel_clearing(self):
        self.ensure_one()
        po = self.purchase_order_id

        if po.state != "clearing":
            raise UserError("สามารถ Cancel Clearing ได้เฉพาะ PO ที่อยู่ใน status Clearing เท่านั้น")

        converted_products = self.env["five.five.product.convert"].search(
            [("purchase_order_id", "=", po.id)]
        )
        converted_products_count = len(converted_products)
        if converted_products:
            converted_products.unlink()

        do_docs = po.document_ids.filtered(lambda doc: doc.type == "do")
        if do_docs:
            do_docs.with_context(skip_po_document_state_check=True).unlink()

        po.message_post(
            body=(
                f"ยกเลิกการ Clearing PO หมายเลข {po.number} "
                f"(ลบ Converted Products {converted_products_count} รายการ, "
                f"ลบเอกสาร DO {len(do_docs)} รายการ และล้าง Warehouse/Logistic)"
            )
        )
        po.write(
            {
                "state": "documents_completed",
                "warehouse_id": False,
                "logistic_id": False,
            }
        )

        return {"type": "ir.actions.act_window_close"}
