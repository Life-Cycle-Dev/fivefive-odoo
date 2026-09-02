from odoo import api, fields, models
from odoo.exceptions import UserError


class CommercialInvoiceLineConvertAddLineWizard(models.TransientModel):
    _name = "five.five.commercial.invoice.line.convert.add.line.wizard"
    _description = "Add/Edit convert line wizard"

    wizard_id = fields.Many2one(
        "five.five.commercial.invoice.line.convert.wizard",
        required=True,
        ondelete="cascade",
    )
    wizard_line_id = fields.Many2one(
        "five.five.commercial.invoice.line.convert.wizard.line",
        string="Convert Line",
        ondelete="cascade",
    )

    commercial_invoice_line_name = fields.Char(
        string="Commercial Invoice Name",
        compute="_compute_commercial_invoice_line_info",
        readonly=True,
        store=False,
    )
    commercial_invoice_unit_id = fields.Many2one(
        "five.five.product.unit",
        string="Unit",
        compute="_compute_commercial_invoice_line_info",
        readonly=True,
        store=False,
    )
    commercial_invoice_size_id = fields.Many2one(
        "five.five.product.size",
        string="Size",
        compute="_compute_commercial_invoice_line_info",
        readonly=True,
        store=False,
    )
    commercial_invoice_grade_id = fields.Many2one(
        "five.five.product.grade",
        string="Grade",
        compute="_compute_commercial_invoice_line_info",
        readonly=True,
        store=False,
    )
    commercial_invoice_quantity = fields.Float(
        string="CI Quantity",
        compute="_compute_commercial_invoice_line_info",
        readonly=True,
        store=False,
    )

    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="Product Variant",
        required=False,
    )
    size_id = fields.Many2one(
        "five.five.product.size",
        related="product_variant_id.size_id",
        string="Size",
        readonly=True,
    )
    size_name = fields.Char(
        string="Size",
        related="size_id.name",
        readonly=True,
    )
    quantity = fields.Float(string="Quantity", required=False, default=1.0)
    quality_note = fields.Char(string="Quality Note", required=False)
    quality_image = fields.Image(string="Quality Image", max_width=1920, max_height=1920)
    item_number = fields.Char(string="Item Number")
    container_number = fields.Char(string="Container No.")
    lot_number = fields.Char(string="Lot Number")
    convert_date = fields.Date(string="Date", default=fields.Date.context_today)
    brand_id = fields.Many2one("five.five.product.brand", string="Brand")
    description_id = fields.Many2one("five.five.product.description", string="Description")
    weight_per_qty = fields.Float(string="Weight per Qty")

    @api.depends("wizard_id.commercial_invoice_line_id")
    def _compute_commercial_invoice_line_info(self):
        for wiz in self:
            cil = wiz.wizard_id.commercial_invoice_line_id if wiz.wizard_id else False
            wiz.commercial_invoice_line_name = cil.name if cil else False
            wiz.commercial_invoice_unit_id = cil.unit_id if cil else False
            wiz.commercial_invoice_size_id = cil.size_id if cil else False
            wiz.commercial_invoice_grade_id = cil.grade_id if cil else False
            wiz.commercial_invoice_quantity = cil.quantity if cil else 0.0

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        wizard_id = res.get("wizard_id") or self.env.context.get("default_wizard_id")
        if wizard_id:
            wizard = self.env["five.five.commercial.invoice.line.convert.wizard"].browse(wizard_id)
            cil = wizard.commercial_invoice_line_id
            if cil:
                res.setdefault("weight_per_qty", cil.weight_per_qty)
                po = cil.purchase_order_id
                if po and po.shipment_container_number:
                    res.setdefault("container_number", po.shipment_container_number)
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.wizard_id:
            raise UserError("ไม่พบข้อมูล Wizard")
        if not self.product_variant_id:
            raise UserError("กรุณาเลือก Product Variant")
        if self.quantity <= 0:
            raise UserError("Quantity ต้องมากกว่า 0")
        if not (self.quality_note or "").strip():
            raise UserError("กรุณากรอก Quality Note")
        if not (self.container_number or "").strip():
            raise UserError("กรุณากรอก Container No.")

        vals = {
            "wizard_id": self.wizard_id.id,
            "product_variant_id": self.product_variant_id.id,
            "quantity": self.quantity,
            "quality_note": self.quality_note.strip(),
            "quality_image": self.quality_image,
            "item_number": self.item_number,
            "container_number": self.container_number,
            "lot_number": self.lot_number,
            "convert_date": self.convert_date,
            "brand_id": self.brand_id.id if self.brand_id else False,
            "description_id": self.description_id.id if self.description_id else False,
            "weight_per_qty": self.weight_per_qty,
        }

        if self.wizard_line_id:
            self.wizard_line_id.write(vals)
        else:
            self.env["five.five.commercial.invoice.line.convert.wizard.line"].create(vals)

        # Re-open parent wizard so user doesn't lose context
        return {
            "type": "ir.actions.act_window",
            "name": "Convert to Product",
            "res_model": "five.five.commercial.invoice.line.convert.wizard",
            "res_id": self.wizard_id.id,
            "view_mode": "form",
            "target": "new",
            "context": {},
        }

