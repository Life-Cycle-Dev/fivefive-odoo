from odoo import _, api, models, fields
from odoo.exceptions import UserError, ValidationError


class ProductConvert(models.Model):
    _name = "five.five.product.convert"
    _description = "Product Convert"

    commercial_invoice_line_id = fields.Many2one(
        "five.five.commercial.invoice.line",
        string="Invoice Line",
        required=False,
        ondelete="cascade",
    )

    is_manual_receipt = fields.Boolean(
        string="Manual Warehouse Receipt",
        default=False,
        index=True,
    )

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        ondelete="cascade",
        index=True,
    )

    po_state = fields.Selection(
        related="purchase_order_id.state",
        string="PO State",
        store=False,
    )

    country_id = fields.Many2one(
        "res.country",
        string="Country",
        related="purchase_order_id.country_id",
        store=True,
        readonly=True,
    )

    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="Product Variant",
        required=True,
        ondelete="cascade",
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
        store=True,
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

    @api.depends("quantity", "weight_per_qty")
    def _compute_total_weight(self):
        for rec in self:
            rec.total_weight = (rec.quantity or 0.0) * (rec.weight_per_qty or 0.0)

    @api.depends(
        "product_cost_ids.cost",
        "product_cost_ids.type",
        "product_cost_ids.start_calculate_cost",
        "quantity",
    )
    def _compute_cost_summary(self):
        ProductCost = self.env["five.five.product.cost"]
        as_of_date = fields.Date.context_today(self)
        for rec in self:
            totals = ProductCost.compute_convert_cost_totals(rec, as_of_date=as_of_date)
            rec.cost_summary = ProductCost.format_cost_amount_summary(totals)

    def _ff_check_po_not_closed_for_convert_mutation(self):
        if self.env.context.get("skip_po_closed_convert_check"):
            return
        for rec in self:
            po = rec.purchase_order_id
            if po and po.state == "closed":
                raise UserError(
                    _("Cannot modify converted products after the purchase order is closed.")
                )

    def unlink(self):
        self._ff_check_po_not_closed_for_convert_mutation()
        ci_lines = self.mapped("commercial_invoice_line_id")
        res = super().unlink()
        for line in ci_lines:
            if line and not line.product_convert_ids:
                line.with_context(skip_po_ci_line_state_check=True).write(
                    {"is_convert_to_product": False}
                )
            else:
                line._ff_recompute_auto_fixed_costs_for_converts()
        return res

    @api.constrains("commercial_invoice_line_id", "is_manual_receipt", "purchase_order_id")
    def _check_manual_receipt_source(self):
        for rec in self:
            if rec.is_manual_receipt and (rec.commercial_invoice_line_id or rec.purchase_order_id):
                raise ValidationError(_("Manual warehouse receipt cannot be linked to a PO or commercial invoice line."))
            if not rec.is_manual_receipt and not rec.commercial_invoice_line_id and not rec.purchase_order_id:
                raise ValidationError(_("Converted product must be linked to a commercial invoice line or purchase order."))

    def _ff_prepare_purchase_order_id(self, vals):
        if vals.get("commercial_invoice_line_id") and not vals.get("purchase_order_id"):
            cil = self.env["five.five.commercial.invoice.line"].browse(vals["commercial_invoice_line_id"])
            if cil.purchase_order_id:
                vals["purchase_order_id"] = cil.purchase_order_id.id

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("skip_po_closed_convert_check"):
            ci_line_ids = [
                vals["commercial_invoice_line_id"]
                for vals in vals_list
                if vals.get("commercial_invoice_line_id")
            ]
            if ci_line_ids:
                po_states = (
                    self.env["five.five.commercial.invoice.line"]
                    .browse(ci_line_ids)
                    .mapped("purchase_order_id.state")
                )
                if any(state == "closed" for state in po_states):
                    raise UserError(
                        _("Cannot modify converted products after the purchase order is closed.")
                    )
            po_ids = [vals["purchase_order_id"] for vals in vals_list if vals.get("purchase_order_id")]
            if po_ids:
                closed = self.env["five.five.purchase.order"].browse(po_ids).filtered(lambda po: po.state == "closed")
                if closed:
                    raise UserError(
                        _("Cannot modify converted products after the purchase order is closed.")
                    )
        for vals in vals_list:
            self._ff_prepare_purchase_order_id(vals)
        records = super().create(vals_list)
        ci_lines = records.filtered(lambda rec: not rec.is_manual_receipt).mapped("commercial_invoice_line_id")
        if ci_lines:
            ci_lines._ff_recompute_auto_fixed_costs_for_converts()
        return records

    def write(self, vals):
        self._ff_check_po_not_closed_for_convert_mutation()
        manual_records = self.filtered("is_manual_receipt")
        ci_records = self - manual_records
        ci_lines_before = ci_records.mapped("commercial_invoice_line_id")
        res = super().write(vals)
        ci_lines_after = ci_records.mapped("commercial_invoice_line_id")
        ci_lines = ci_lines_before | ci_lines_after
        if ci_lines and any(k in vals for k in ("quantity", "weight_per_qty", "commercial_invoice_line_id")):
            ci_lines._ff_recompute_auto_fixed_costs_for_converts()
        if "quantity" in vals:
            inventories = self.env["five.five.inventory"].search([("product_convert_id", "in", self.ids)])
            for inventory in inventories:
                recalc_vals = inventory._get_recalculate_cost_values(
                    as_of_date=fields.Date.context_today(self)
                )
                if recalc_vals:
                    inventory.write(recalc_vals)
        return res

    def action_open_form(self):
        self.ensure_one()
        self._ff_check_po_not_closed_for_convert_mutation()
        return {
            "type": "ir.actions.act_window",
            "name": "Product Convert",
            "res_model": "five.five.product.convert",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
