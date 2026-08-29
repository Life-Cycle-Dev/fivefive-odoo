import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CommercialInvoiceLineConvertWizard(models.TransientModel):
    _name = "five.five.commercial.invoice.line.convert.wizard"
    _description = "Convert commercial invoice line to products wizard"

    commercial_invoice_line_id = fields.Many2one(
        "five.five.commercial.invoice.line",
        string="Commercial Invoice Line",
        required=True,
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
    commercial_invoice_total_weight = fields.Float(
        string="CI Total Weight",
        compute="_compute_commercial_invoice_line_info",
        readonly=True,
        store=False,
    )
    commercial_invoice_unit_price = fields.Float(
        string="Unit Price/Weight",
        compute="_compute_commercial_invoice_line_info",
        readonly=True,
        store=False,
    )
    converted_total_weight = fields.Float(
        string="Received Total Weight",
        compute="_compute_weight_diff",
        readonly=True,
        store=False,
    )
    weight_diff = fields.Float(
        string="Weight Diff (Received - CI)",
        compute="_compute_weight_diff",
        readonly=True,
        store=False,
    )
    price_diff_usd = fields.Float(
        string="Price Diff",
        compute="_compute_weight_diff",
        readonly=True,
        store=False,
    )

    convert_line_ids = fields.One2many(
        "five.five.commercial.invoice.line.convert.wizard.line",
        "wizard_id",
        string="Convert Lines",
    )

    @api.depends("commercial_invoice_line_id")
    def _compute_commercial_invoice_line_info(self):
        for wiz in self:
            cil = wiz.commercial_invoice_line_id
            wiz.commercial_invoice_line_name = cil.name if cil else False
            wiz.commercial_invoice_unit_id = cil.unit_id if cil else False
            wiz.commercial_invoice_size_id = cil.size_id if cil else False
            wiz.commercial_invoice_grade_id = cil.grade_id if cil else False
            wiz.commercial_invoice_quantity = cil.quantity if cil else 0.0
            wiz.commercial_invoice_total_weight = cil.total_weight if cil else 0.0
            wiz.commercial_invoice_unit_price = cil.unit_price_usd if cil else 0.0

    @api.depends(
        "convert_line_ids.quantity",
        "convert_line_ids.weight_per_qty",
        "commercial_invoice_total_weight",
        "commercial_invoice_unit_price",
    )
    def _compute_weight_diff(self):
        for wiz in self:
            received_weight = sum(
                (line.quantity or 0.0) * (line.weight_per_qty or 0.0)
                for line in wiz.convert_line_ids
            )
            wiz.converted_total_weight = received_weight
            ci_weight = wiz.commercial_invoice_total_weight or 0.0
            wiz.weight_diff = received_weight - ci_weight
            wiz.price_diff_usd = wiz.weight_diff * (wiz.commercial_invoice_unit_price or 0.0)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        cil_id = res.get("commercial_invoice_line_id") or self.env.context.get(
            "default_commercial_invoice_line_id"
        )
        if not cil_id:
            return res

        # Ensure the M2O default is always set (avoids _unknown values during web_read/onchange)
        res["commercial_invoice_line_id"] = cil_id
        return res

    def action_confirm(self):
        self.ensure_one()

        cil = self.commercial_invoice_line_id
        if not cil:
            raise UserError("ไม่พบข้อมูล Commercial Invoice Line")

        po = cil.purchase_order_id
        if po and po.state == "closed":
            raise UserError("ไม่สามารถ Convert ได้เมื่อ PO ถูก Close แล้ว")

        if not self.convert_line_ids:
            raise UserError("กรุณาเพิ่มรายการ Product ที่ต้องการ Convert อย่างน้อย 1 รายการ")

        for line in self.convert_line_ids:
            if not line.product_variant_id:
                raise UserError("กรุณาเลือก Product ให้ครบทุกบรรทัด")
            if line.quantity <= 0:
                raise UserError("Quantity ต้องมากกว่า 0")
            if not (line.quality_note or "").strip():
                raise UserError("กรุณากรอก Quality Note ให้ครบทุกบรรทัด")

        convert_vals_list = []
        cil = self.commercial_invoice_line_id
        po = cil.purchase_order_id
        default_container = po.shipment_container_number if po else False
        for line in self.convert_line_ids:
            convert_vals_list.append(
                {
                    "commercial_invoice_line_id": cil.id,
                    "purchase_order_id": po.id if po else False,
                    "product_variant_id": line.product_variant_id.id,
                    "quantity": line.quantity,
                    "quality_note": line.quality_note.strip(),
                    "quality_image": line.quality_image,
                    "item_number": line.item_number,
                    "container_number": line.container_number or default_container,
                    "lot_number": line.lot_number,
                    "convert_date": line.convert_date,
                    "brand_id": line.brand_id.id if line.brand_id else False,
                    "description_id": line.description_id.id if line.description_id else False,
                    "weight_per_qty": line.weight_per_qty or cil.weight_per_qty,
                }
            )

        self.env["five.five.product.convert"].create(convert_vals_list)
        # Auto-create/recompute fixed costs derived from CI for all converts of this CI line.
        cil._ff_recompute_auto_fixed_costs_for_converts()
        cil.with_context(skip_po_ci_line_state_check=True).write(
            {"is_convert_to_product": True}
        )

        return {"type": "ir.actions.act_window_close"}

    def action_open_add_convert_line_wizard(self):
        self.ensure_one()
        wiz = self.env["five.five.commercial.invoice.line.convert.add.line.wizard"].create(
            {"wizard_id": self.id}
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Add Convert Line",
            "res_model": "five.five.commercial.invoice.line.convert.add.line.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
            "context": {},
        }


class CommercialInvoiceLineConvertWizardLine(models.TransientModel):
    _name = "five.five.commercial.invoice.line.convert.wizard.line"
    _description = "Convert wizard line"

    wizard_id = fields.Many2one(
        "five.five.commercial.invoice.line.convert.wizard",
        required=True,
        ondelete="cascade",
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

    quantity = fields.Float(
        string="Quantity",
        required=True,
        default=1.0,
    )

    quality_note = fields.Char(
        string="Quality Note",
        required=True,
    )
    quality_image = fields.Image(
        string="Quality Image",
        max_width=1920,
        max_height=1920,
    )
    item_number = fields.Char(string="Item Number")
    container_number = fields.Char(string="Container No.")
    lot_number = fields.Char(string="Lot Number")
    convert_date = fields.Date(string="Date", default=fields.Date.context_today)
    brand_id = fields.Many2one("five.five.product.brand", string="Brand")
    description_id = fields.Many2one("five.five.product.description", string="Description")
    weight_per_qty = fields.Float(string="Weight per Qty")
    total_weight = fields.Float(
        string="Total Weight",
        compute="_compute_total_weight",
        readonly=True,
    )

    cost_payload = fields.Text(string="Costs (JSON)", default="[]")
    cost_summary = fields.Char(string="Cost Summary", compute="_compute_cost_summary")

    @api.depends("quantity", "weight_per_qty")
    def _compute_total_weight(self):
        for line in self:
            line.total_weight = (line.quantity or 0.0) * (line.weight_per_qty or 0.0)

    def _parse_cost_payload(self):
        self.ensure_one()
        try:
            data = json.loads(self.cost_payload or "[]")
        except Exception:
            return []
        return data if isinstance(data, list) else []

    @api.depends("cost_payload", "quantity")
    def _compute_cost_summary(self):
        for line in self:
            costs = []
            try:
                costs = json.loads(line.cost_payload or "[]") or []
            except Exception:
                costs = []

            totals = {"fixed": 0.0, "daily": 0.0, "weekly": 0.0, "monthly": 0.0, "yearly": 0.0}
            for c in costs if isinstance(costs, list) else []:
                ctype = (c or {}).get("type")
                try:
                    val = float((c or {}).get("cost") or 0.0)
                except Exception:
                    val = 0.0
                if ctype in totals:
                    totals[ctype] += val

            line.cost_summary = self.env["five.five.product.cost"].format_cost_type_summary(totals)

    def action_open_cost_wizard(self):
        self.ensure_one()
        wiz = self.env["five.five.product.convert.cost.wizard"].create(
            {"convert_wizard_line_id": self.id, "cost_payload": self.cost_payload or "[]"}
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Edit Costs",
            "res_model": "five.five.product.convert.cost.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
            "context": {},
        }

    def action_open_edit_convert_line_wizard(self):
        self.ensure_one()
        wiz = self.env["five.five.commercial.invoice.line.convert.add.line.wizard"].create(
            {
                "wizard_id": self.wizard_id.id,
                "wizard_line_id": self.id,
                "product_variant_id": self.product_variant_id.id if self.product_variant_id else False,
                "quantity": self.quantity,
                "quality_note": self.quality_note,
                "quality_image": self.quality_image,
                "item_number": self.item_number,
                "container_number": self.container_number,
                "lot_number": self.lot_number,
                "convert_date": self.convert_date,
                "brand_id": self.brand_id.id if self.brand_id else False,
                "description_id": self.description_id.id if self.description_id else False,
                "weight_per_qty": self.weight_per_qty,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Edit Convert Line",
            "res_model": "five.five.commercial.invoice.line.convert.add.line.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
            "context": {},
        }

