from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class Inventory(models.Model):
    _name = "five.five.inventory"
    _description = "Inventory"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="Product Variant",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        "five.five.warehouse",
        string="Warehouse",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    lot_number = fields.Char(string="Lot Number", tracking=True)
    item_number = fields.Char(string="Item Number", tracking=True)
    container_number = fields.Char(string="Container No.", tracking=True)
    brand_id = fields.Many2one("five.five.product.brand", string="Brand", tracking=True)
    description_id = fields.Many2one("five.five.product.description", string="Description", tracking=True)
    product_code = fields.Char(
        string="Code",
        related="product_variant_id.sku",
        readonly=True,
    )
    size_id = fields.Many2one(
        "five.five.product.size",
        string="Size",
        related="product_variant_id.size_id",
        readonly=True,
    )
    size_name = fields.Char(
        string="Size",
        related="size_id.name",
        readonly=True,
    )
    display_date = fields.Date(
        string="Date",
        compute="_compute_display_date",
        store=True,
        readonly=True,
    )
    weight_per_qty = fields.Float(string="Weight per Qty", tracking=True)
    total_weight = fields.Float(string="Total Weight", tracking=True)
    quantity = fields.Float(string="Quantity", tracking=True, aggregator="sum")
    quality_note = fields.Char(string="Quality Note", tracking=True)
    quality_image = fields.Image(string="Quality Image", max_width=1920, max_height=1920)
    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        ondelete="set null",
        index=True,
        readonly=True,
        tracking=True,
    )
    product_convert_id = fields.Many2one(
        "five.five.product.convert",
        string="Converted Product",
        ondelete="set null",
        index=True,
        tracking=True,
    )
    cost_summary = fields.Char(string="Cost Summary", tracking=True)
    total_cost_thb = fields.Float(string="Total Cost (THB)", digits=(16, 2), tracking=True)
    unit_cost_thb = fields.Float(
        string="Unit Cost (THB)",
        compute="_compute_unit_cost_thb",
        digits=(16, 2),
    )
    cost_as_of_date = fields.Date(
        string="Cost As Of",
        default=fields.Date.context_today,
        readonly=True,
        help="วันที่ใช้คำนวณต้นทุนรวม (อัปเดตอัตโนมัติทุกวัน)",
        tracking=True,
    )
    po_closed_date = fields.Date(
        string="PO Closed Date",
        readonly=True,
        tracking=True,
    )

    @api.depends("product_convert_id.convert_date", "po_closed_date")
    def _compute_display_date(self):
        for inventory in self:
            inventory.display_date = (
                inventory.product_convert_id.convert_date or inventory.po_closed_date
            )

    @api.depends("total_cost_thb", "quantity")
    def _compute_unit_cost_thb(self):
        for inventory in self:
            if inventory.quantity > 0:
                inventory.unit_cost_thb = inventory.total_cost_thb / inventory.quantity
            else:
                inventory.unit_cost_thb = 0.0

    def _get_cost_values_for_quantity(self, quantity, as_of_date=None):
        self.ensure_one()
        ProductCost = self.env["five.five.product.cost"]
        if not self.product_convert_id:
            if float_is_zero(self.quantity, precision_digits=6):
                return {
                    "cost_summary": _("No costs"),
                    "total_cost_thb": 0.0,
                }
            ratio = quantity / self.quantity
            new_total = self.total_cost_thb * ratio
            return {
                "cost_summary": ProductCost.format_frozen_store_cost_summary(new_total),
                "total_cost_thb": new_total,
            }

        as_of_date = (
            ProductCost._normalize_date(as_of_date)
            or ProductCost._normalize_date(self.cost_as_of_date)
            or fields.Date.context_today(self)
        )
        convert = self.product_convert_id
        convert.invalidate_recordset(["product_cost_ids"])
        costs = ProductCost.search([("product_convert_id", "=", convert.id)])
        costs.invalidate_recordset(["start_calculate_cost", "cost", "type"])

        totals = ProductCost.compute_convert_cost_totals(convert, as_of_date=as_of_date)
        convert_qty = convert.quantity or 0.0
        ratio = quantity / convert_qty if convert_qty else 0.0
        scaled_totals = {key: amount * ratio for key, amount in totals.items()}
        return {
            "cost_summary": ProductCost.format_cost_amount_summary(scaled_totals),
            "total_cost_thb": sum(scaled_totals.values()),
        }

    def _get_recalculate_cost_values(self, as_of_date=None):
        self.ensure_one()
        if not self.product_convert_id:
            return {}

        as_of_date = (
            self.env["five.five.product.cost"]._normalize_date(as_of_date)
            or self.env["five.five.product.cost"]._normalize_date(self.cost_as_of_date)
            or fields.Date.context_today(self)
        )
        cost_vals = self._get_cost_values_for_quantity(self.quantity, as_of_date=as_of_date)
        return {
            **cost_vals,
            "cost_as_of_date": as_of_date,
        }

    def _weight_for_qty(self, qty):
        self.ensure_one()
        wpq = self.weight_per_qty or 0.0
        if not float_is_zero(wpq, precision_digits=6):
            return qty * wpq
        if self.quantity and self.total_weight:
            return self.total_weight * (qty / self.quantity)
        return 0.0

    def _consume_quantity(self, consumed_qty):
        """Reduce on-hand quantity after a transfer or allocation."""
        self.ensure_one()
        if float_compare(consumed_qty, 0, precision_digits=6) <= 0:
            raise UserError(_("Consumed quantity must be greater than zero."))
        if float_compare(consumed_qty, self.quantity, precision_digits=6) > 0:
            raise UserError(_("Consumed quantity exceeds available quantity."))

        remaining_qty = self.quantity - consumed_qty
        if float_is_zero(remaining_qty, precision_digits=6):
            ProductCost = self.env["five.five.product.cost"]
            self.write(
                {
                    "quantity": 0.0,
                    "total_cost_thb": 0.0,
                    "cost_summary": ProductCost.format_frozen_store_cost_summary(0.0),
                }
            )
            return

        cost_vals = self._get_cost_values_for_quantity(remaining_qty)
        self.write({"quantity": remaining_qty, **cost_vals})

    def action_recalculate_cost(self):
        for record in self:
            vals = record._get_recalculate_cost_values(
                as_of_date=fields.Date.context_today(self)
            )
            if vals:
                record.write(vals)
        return True

    def action_open_edit_costs(self):
        self.ensure_one()
        if not self.product_convert_id:
            raise UserError(_("No converted product linked to this inventory line."))
        return self.product_convert_id.action_open_form()

    def action_open_purchase_order(self):
        self.ensure_one()
        if not self.purchase_order_id:
            raise UserError(_("No purchase order linked to this inventory line."))
        return {
            "type": "ir.actions.act_window",
            "name": "Purchase Order",
            "res_model": "five.five.purchase.order",
            "view_mode": "form",
            "res_id": self.purchase_order_id.id,
            "target": "current",
        }

    def action_open_transfer_wizard(self):
        inventories = self.filtered(lambda inv: inv.quantity > 0)
        if not inventories:
            raise UserError(_("No available quantity to transfer."))
        return {
            "type": "ir.actions.act_window",
            "name": "Transfer to Store",
            "res_model": "five.five.warehouse.transfer.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_warehouse_id": inventories[0].warehouse_id.id,
                "default_product_variant_id": inventories[0].product_variant_id.id,
                "default_inventory_ids": inventories.ids,
            },
        }

    @api.model
    def _cron_recalculate_daily_costs(self):
        today = fields.Date.context_today(self)
        inventories = self.search([("product_convert_id", "!=", False)])
        for inventory in inventories:
            vals = inventory._get_recalculate_cost_values(as_of_date=today)
            if vals:
                inventory.with_context(mail_notrack=True).write(vals)
