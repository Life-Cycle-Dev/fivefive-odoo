from odoo import api, fields, models
from odoo.exceptions import UserError

_ALLOWED_PO_STATES_FOR_LINES = ("draft", "po_issued")


class CommercialInvoiceLine(models.Model):
    _name = "five.five.commercial.invoice.line"
    _description = "Commercial Invoice Line"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        ondelete="cascade",
        index=True,
    )

    name = fields.Char(string="Name", required=True)
    unit_id = fields.Many2one(
        "five.five.product.unit",
        string="Unit",
        required=True,
    )
    size_id = fields.Many2one(
        "five.five.product.size",
        required=True,
        string="Size",
    )
    grade_id = fields.Many2one(
        "five.five.product.grade",
        string="Grade",
        required=True,
    )
    unit_price_usd = fields.Float(string="Unit Price (USD)", required=True)
    quantity = fields.Float(string="Quantity", required=True)
    total_price_usd = fields.Float(string="Total Price (USD)", compute="_compute_total_price", store=True)

    po_state = fields.Selection(
        related="purchase_order_id.state",
        string="PO State",
        store=False,
    )
    is_convert_to_product = fields.Boolean(string="Convert to Product", default=False)
    product_convert_ids = fields.One2many(
        "five.five.product.convert",
        "commercial_invoice_line_id",
        string="Product Convert Lines",
        copy=False,
    )

    @api.depends("unit_price_usd", "quantity")
    def _compute_total_price(self):
        for line in self:
            line.total_price_usd = line.quantity * line.unit_price_usd

    @api.model
    def _ff_po_states_allow_line_mutation(self, purchase_orders):
        if self.env.context.get("skip_po_ci_line_state_check"):
            return
        invalid = purchase_orders.filtered(
            lambda p: p and p.state not in _ALLOWED_PO_STATES_FOR_LINES
        )
        if invalid:
            raise UserError(
                "แก้ไข/เพิ่ม/ลบรายการ Commercial Invoice ได้เฉพาะเมื่อ PO อยู่ใน Draft หรือ PO Issued เท่านั้น"
            )

    @api.model_create_multi
    def create(self, vals_list):
        po_ids = [v["purchase_order_id"] for v in vals_list if v.get("purchase_order_id")]
        if po_ids:
            self._ff_po_states_allow_line_mutation(
                self.env["five.five.purchase.order"].browse(po_ids)
            )
        return super().create(vals_list)

    def write(self, vals):
        orders = self.mapped("purchase_order_id")
        if vals.get("purchase_order_id"):
            orders |= self.env["five.five.purchase.order"].browse(vals["purchase_order_id"])
        self._ff_po_states_allow_line_mutation(orders)
        return super().write(vals)

    def unlink(self):
        self._ff_po_states_allow_line_mutation(self.mapped("purchase_order_id"))
        return super().unlink()

    def action_convert_to_product(self):
        self.ensure_one()
        if self.is_convert_to_product:
            raise UserError("รายการนี้ถูก Convert เป็น Product แล้ว")

        wiz = self.env["five.five.commercial.invoice.line.convert.wizard"].create(
            {"commercial_invoice_line_id": self.id}
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Convert to Product",
            "res_model": "five.five.commercial.invoice.line.convert.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
            "context": {},
        }

    def action_open_product_converts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Converted Products",
            "res_model": "five.five.product.convert",
            "view_mode": "list,form",
            "target": "current",
            "domain": [("commercial_invoice_line_id", "=", self.id)],
            "context": {"default_commercial_invoice_line_id": self.id},
        }

    def action_unconvert_products(self):
        for line in self:
            converts = line.product_convert_ids
            if converts:
                converts.unlink()
            line.with_context(skip_po_ci_line_state_check=True).write(
                {"is_convert_to_product": False}
            )
        return True
