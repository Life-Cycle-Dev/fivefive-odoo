from odoo import api, models, fields


class ProductConvert(models.Model):
    _name = "five.five.product.convert"
    _description = "Product Convert"

    commercial_invoice_line_id = fields.Many2one(
        "five.five.commercial.invoice.line",
        string="Invoice Line",
        required=True,
        ondelete="cascade",
    )

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        related="commercial_invoice_line_id.purchase_order_id",
        store=True,
        index=True,
        readonly=True,
    )

    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="Product Variant",
        required=True,
        ondelete="cascade",
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

    product_cost_ids = fields.One2many(
        "five.five.product.cost",
        "product_convert_id",
        string="Product Costs",
    )

    cost_summary = fields.Char(
        string="Cost Summary",
        compute="_compute_cost_summary",
        store=False,
    )

    @api.depends("product_cost_ids.cost", "product_cost_ids.type")
    def _compute_cost_summary(self):
        for rec in self:
            totals = {"fixed": 0.0, "daily": 0.0, "weekly": 0.0, "monthly": 0.0, "yearly": 0.0}
            for c in rec.product_cost_ids:
                if c.type in totals:
                    totals[c.type] += c.cost or 0.0

            parts = []
            for k in ["fixed", "daily", "weekly", "monthly", "yearly"]:
                if totals[k]:
                    parts.append(f"{k}={totals[k]:.2f} per qty")
            rec.cost_summary = ", ".join(parts) if parts else "No costs"

    def unlink(self):
        ci_lines = self.mapped("commercial_invoice_line_id")
        res = super().unlink()
        # If a CI line has no converts left, mark it as unconverted.
        for line in ci_lines:
            if line and not line.product_convert_ids:
                line.with_context(skip_po_ci_line_state_check=True).write(
                    {"is_convert_to_product": False}
                )
        return res

    def action_open_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Product Convert",
            "res_model": "five.five.product.convert",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
