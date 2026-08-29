from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class StoreInventory(models.Model):
    _name = "five.five.store.inventory"
    _description = "Store Inventory"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "lot_number"

    store_id = fields.Many2one(
        "five.five.store",
        string="Store",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="Product Variant",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    sell_price_thb = fields.Float(
        related="product_variant_id.sell_price_thb",
        string="Sell Price (THB)",
        readonly=False,
        digits=(16, 2),
    )
    lot_number = fields.Char(string="Lot Number", required=True, tracking=True)
    brand_id = fields.Many2one("five.five.product.brand", string="Brand", tracking=True)
    description_id = fields.Many2one("five.five.product.description", string="Description", tracking=True)
    weight_per_qty = fields.Float(string="Weight per Qty", tracking=True)
    total_weight = fields.Float(string="Total Weight", tracking=True)
    quantity = fields.Float(string="Quantity", tracking=True)
    quality_note = fields.Char(string="Quality Note", tracking=True)
    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        ondelete="set null",
        readonly=True,
        tracking=True,
    )
    source_inventory_id = fields.Many2one(
        "five.five.inventory",
        string="Source Warehouse Inventory",
        ondelete="set null",
        tracking=True,
    )
    cost_summary = fields.Char(string="Cost Summary", tracking=True)
    total_cost_thb = fields.Float(string="Total Cost (THB)", digits=(16, 2), tracking=True)
    cost_as_of_date = fields.Date(
        string="Cost Frozen On",
        tracking=True,
        help="วันที่ freeze ต้นทุนเป็น Fixed เมื่อย้ายเข้า Store",
    )

    _sql_constraints = [
        (
            "five_five_store_inventory_store_lot_uniq",
            "unique(store_id, lot_number)",
            "Lot number must be unique per store.",
        ),
    ]

    def _weight_per_qty(self):
        self.ensure_one()
        return self.weight_per_qty or 0.0

    def _weight_for_qty(self, qty):
        self.ensure_one()
        wpq = self._weight_per_qty()
        if not float_is_zero(wpq, precision_digits=6):
            return qty * wpq
        if self.quantity and self.total_weight:
            return self.total_weight * (qty / self.quantity)
        return 0.0

    def _qty_for_weight(self, weight):
        self.ensure_one()
        wpq = self._weight_per_qty()
        if float_is_zero(wpq, precision_digits=6):
            raise UserError(
                _("Weight per qty is required for %(product)s (Lot %(lot)s).")
                % {
                    "product": self.product_variant_id.display_name,
                    "lot": self.lot_number or "-",
                }
            )
        return weight / wpq

    def _apply_stock_update(self, quantity, total_cost_thb, total_weight=None):
        self.ensure_one()
        ProductCost = self.env["five.five.product.cost"]
        vals = {
            "quantity": quantity,
            "total_cost_thb": total_cost_thb,
            "cost_summary": ProductCost.format_frozen_store_cost_summary(total_cost_thb),
        }
        if total_weight is not None:
            vals["total_weight"] = total_weight
        elif self.weight_per_qty:
            vals["total_weight"] = quantity * self.weight_per_qty
        self.write(vals)

    def _convert_to_variant(self, target_variant, convert_qty):
        """Reclassify store stock to another variant (same physical lot when converting all qty)."""
        self.ensure_one()
        if not target_variant:
            raise UserError(_("Please select the target product variant."))
        if target_variant == self.product_variant_id:
            raise UserError(
                _("Target product must be different from source product (%(product)s).")
                % {"product": self.product_variant_id.display_name}
            )
        if float_compare(convert_qty, 0, precision_digits=6) <= 0:
            raise UserError(_("Convert quantity must be greater than zero."))
        if float_compare(convert_qty, self.quantity or 0.0, precision_digits=6) > 0:
            raise UserError(
                _(
                    "Convert quantity (%(convert)s) exceeds available quantity (%(available)s) "
                    "for %(product)s (Lot %(lot)s)."
                )
                % {
                    "convert": convert_qty,
                    "available": self.quantity,
                    "product": self.product_variant_id.display_name,
                    "lot": self.lot_number or "-",
                }
            )

        old_qty = self.quantity or 0.0
        old_weight = self.total_weight or self._weight_for_qty(old_qty)
        old_cost = self.total_cost_thb or 0.0
        is_full = float_is_zero(old_qty - convert_qty, precision_digits=6)

        if is_full:
            self.write({"product_variant_id": target_variant.id})
            return self

        transfer_cost = old_cost * (convert_qty / old_qty) if old_qty else 0.0
        transfer_weight = self._weight_for_qty(convert_qty)
        self._apply_stock_update(
            old_qty - convert_qty,
            old_cost - transfer_cost,
            old_weight - transfer_weight,
        )

        StoreInventory = self.env["five.five.store.inventory"]
        existing_target = StoreInventory.search(
            [
                ("store_id", "=", self.store_id.id),
                ("product_variant_id", "=", target_variant.id),
            ],
            order="id",
            limit=1,
        )
        if existing_target:
            existing_target._apply_stock_update(
                existing_target.quantity + convert_qty,
                existing_target.total_cost_thb + transfer_cost,
                (existing_target.total_weight or 0.0) + transfer_weight,
            )
            return existing_target

        return StoreInventory.create(
            {
                "store_id": self.store_id.id,
                "product_variant_id": target_variant.id,
                "lot_number": self._suggest_convert_target_lot(),
                "quantity": convert_qty,
                "quality_note": self.quality_note,
                "brand_id": self.brand_id.id if self.brand_id else False,
                "description_id": self.description_id.id if self.description_id else False,
                "weight_per_qty": self.weight_per_qty,
                "total_weight": transfer_weight,
                "purchase_order_id": self.purchase_order_id.id,
                "source_inventory_id": self.source_inventory_id.id,
                "total_cost_thb": transfer_cost,
                "cost_summary": self.env["five.five.product.cost"].format_frozen_store_cost_summary(
                    transfer_cost
                ),
                "cost_as_of_date": self.cost_as_of_date,
            }
        )

    def _suggest_convert_target_lot(self):
        self.ensure_one()
        base = f"{(self.lot_number or 'LOT').strip()}-CV"
        StoreInventory = self.env["five.five.store.inventory"]
        candidate = base
        seq = 1
        while StoreInventory.search_count(
            [("store_id", "=", self.store_id.id), ("lot_number", "=", candidate)]
        ):
            seq += 1
            candidate = f"{base}{seq}"
        return candidate

    def action_open_convert_wizard(self):
        self.ensure_one()
        if float_compare(self.quantity or 0.0, 0, precision_digits=6) <= 0:
            raise UserError(_("No quantity available to convert."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Convert Product"),
            "res_model": "five.five.store.inventory.convert.wizard",
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "fivefive_custom.view_five_five_store_inventory_convert_wizard_single_form"
                    ).id,
                    "form",
                )
            ],
            "target": "new",
            "context": {
                "default_store_id": self.store_id.id,
                "default_store_inventory_id": self.id,
                "convert_from_line": True,
            },
        }


class Store(models.Model):
    _inherit = "five.five.store"

    store_inventory_ids = fields.One2many(
        "five.five.store.inventory",
        "store_id",
        string="Store Inventory",
        tracking=True,
    )
    store_inventory_total_cost_thb = fields.Float(
        string="Total Store Inventory Cost (THB)",
        compute="_compute_store_inventory_total_cost_thb",
        digits=(16, 2),
    )

    @api.depends("store_inventory_ids.total_cost_thb")
    def _compute_store_inventory_total_cost_thb(self):
        for store in self:
            store.store_inventory_total_cost_thb = sum(store.store_inventory_ids.mapped("total_cost_thb"))

    def action_open_transfer_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Transfer to Store",
            "res_model": "five.five.warehouse.transfer.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_store_id": self.id,
            },
        }

    def action_open_inventory_adjust_wizard(self):
        self.ensure_one()
        if not self.store_inventory_ids:
            raise UserError(_("No store inventory available to adjust."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Adjust Inventory"),
            "res_model": "five.five.store.inventory.adjust.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_store_id": self.id,
            },
        }
