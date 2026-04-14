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
        for line in self.convert_line_ids:
            costs = line._parse_cost_payload()
            cost_commands = []
            for c in costs:
                name = ((c or {}).get("cost_name") or "").strip()
                ctype = (c or {}).get("type")
                cost_val = (c or {}).get("cost")
                if not name:
                    raise UserError("กรุณากรอก Cost Name ให้ครบ")
                if cost_val is None or float(cost_val) < 0:
                    raise UserError("Cost ต้องไม่ติดลบ")
                if ctype not in ("fixed", "daily", "weekly", "monthly", "yearly"):
                    raise UserError("กรุณาเลือก Cost Type ให้ครบ")
                cost_commands.append(
                    (
                        0,
                        0,
                        {
                            "cost_name": name,
                            "cost": float(cost_val),
                            "type": ctype,
                        },
                    )
                )
            convert_vals_list.append(
                {
                    "commercial_invoice_line_id": cil.id,
                    "product_variant_id": line.product_variant_id.id,
                    "quantity": line.quantity,
                    "quality_note": line.quality_note.strip(),
                    "product_cost_ids": cost_commands,
                }
            )

        self.env["five.five.product.convert"].create(convert_vals_list)
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

    quantity = fields.Float(
        string="Quantity",
        required=True,
        default=1.0,
    )

    quality_note = fields.Char(
        string="Quality Note",
        required=True,
    )

    cost_payload = fields.Text(string="Costs (JSON)", default="[]")
    cost_summary = fields.Char(string="Cost Summary", compute="_compute_cost_summary")

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

            parts = []
            for k in ["fixed", "daily", "weekly", "monthly", "yearly"]:
                if totals[k]:
                    # Costs in payload are already "per 1 qty"
                    parts.append(f"{k}={totals[k]:.2f} per qty")
            line.cost_summary = ", ".join(parts) if parts else _("No costs")

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

