import json

from odoo import api, fields, models
from odoo.exceptions import UserError


class ProductConvertCostWizard(models.TransientModel):
    _name = "five.five.product.convert.cost.wizard"
    _description = "Edit costs for product convert wizard line"

    convert_wizard_line_id = fields.Many2one(
        "five.five.commercial.invoice.line.convert.wizard.line",
        required=True,
        ondelete="cascade",
    )

    product_variant_id = fields.Many2one(
        related="convert_wizard_line_id.product_variant_id",
        string="Product Variant",
        readonly=True,
    )
    quantity = fields.Float(
        related="convert_wizard_line_id.quantity",
        string="Quantity",
        readonly=True,
    )
    quality_note = fields.Char(
        related="convert_wizard_line_id.quality_note",
        string="Quality Note",
        readonly=True,
    )

    cost_payload = fields.Text(string="Costs (JSON)", default="[]")

    cost_line_ids = fields.One2many(
        "five.five.product.convert.cost.wizard.line",
        "wizard_id",
        string="Costs",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for wiz in records:
            # Populate editable lines from payload for UI.
            if wiz.cost_payload and not wiz.cost_line_ids:
                wiz._load_payload_to_lines()
        return records

    def _load_payload_to_lines(self):
        self.ensure_one()
        try:
            data = json.loads(self.cost_payload or "[]") or []
        except Exception:
            data = []
        lines = []
        for c in data if isinstance(data, list) else []:
            lines.append(
                (
                    0,
                    0,
                    {
                        "cost_name": (c or {}).get("cost_name") or "",
                        "cost": (c or {}).get("cost") or 0.0,
                        "type": (c or {}).get("type") or "fixed",
                    },
                )
            )
        if lines:
            self.cost_line_ids = lines

    def action_confirm(self):
        self.ensure_one()
        payload = []
        for line in self.cost_line_ids:
            if not (line.cost_name or "").strip():
                raise UserError("กรุณากรอก Cost Name ให้ครบ")
            if line.cost is None or line.cost < 0:
                raise UserError("Cost ต้องไม่ติดลบ")
            if not line.type:
                raise UserError("กรุณาเลือก Cost Type ให้ครบ")
            payload.append(
                {
                    "cost_name": line.cost_name.strip(),
                    "cost": line.cost,
                    "type": line.type,
                }
            )

        self.cost_payload = json.dumps(payload, ensure_ascii=False)
        self.convert_wizard_line_id.cost_payload = self.cost_payload
        parent = self.convert_wizard_line_id.wizard_id
        return {
            "type": "ir.actions.act_window",
            "name": "Convert to Product",
            "res_model": "five.five.commercial.invoice.line.convert.wizard",
            "res_id": parent.id,
            "view_mode": "form",
            "target": "new",
            "context": {},
        }


class ProductConvertCostWizardLine(models.TransientModel):
    _name = "five.five.product.convert.cost.wizard.line"
    _description = "Cost line for cost wizard"

    wizard_id = fields.Many2one(
        "five.five.product.convert.cost.wizard",
        required=True,
        ondelete="cascade",
    )

    cost_name = fields.Char(string="Cost Name", required=True)
    cost = fields.Float(string="Cost (THB)", required=True, digits=(16, 2))
    type = fields.Selection(
        selection=[
            ("fixed", "Fixed"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("yearly", "Yearly"),
        ],
        string="Cost Type",
        required=True,
        default="fixed",
    )

