from odoo import _, api, fields, models


class StoreInventoryAdjustment(models.Model):
    _name = "five.five.store.inventory.adjustment"
    _description = "Store Inventory Adjustment"
    _order = "adjusted_at desc, id desc"

    store_id = fields.Many2one(
        "five.five.store",
        string="Store",
        required=True,
        ondelete="cascade",
        index=True,
    )
    store_inventory_id = fields.Many2one(
        "five.five.store.inventory",
        string="Store Inventory Line",
        ondelete="set null",
        index=True,
    )
    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="Product Variant",
        required=True,
        ondelete="restrict",
        index=True,
    )
    lot_number = fields.Char(string="Lot Number", required=True)
    adjustment_type = fields.Selection(
        [
            ("increase", "Increase"),
            ("decrease", "Decrease"),
        ],
        string="Type",
        required=True,
    )
    quantity_before = fields.Float(string="Qty Before", digits=(16, 6))
    quantity_change = fields.Float(string="Qty Change", digits=(16, 6))
    quantity_after = fields.Float(string="Qty After", digits=(16, 6))
    cost_before = fields.Float(string="Cost Before (THB)", digits=(16, 2))
    cost_after = fields.Float(string="Cost After (THB)", digits=(16, 2))
    reason = fields.Text(string="Reason", required=True)
    user_id = fields.Many2one(
        "res.users",
        string="Adjusted By",
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
    )
    adjusted_at = fields.Datetime(
        string="Adjusted At",
        default=fields.Datetime.now,
        required=True,
        readonly=True,
    )
    name = fields.Char(string="Reference", compute="_compute_name", store=True)

    @api.depends("store_id.name", "product_variant_id.display_name", "lot_number", "adjusted_at")
    def _compute_name(self):
        for record in self:
            store = record.store_id.name or "-"
            product = record.product_variant_id.display_name or "-"
            lot = record.lot_number or "-"
            when = record.adjusted_at.strftime("%Y-%m-%d %H:%M") if record.adjusted_at else "-"
            record.name = f"{store} / {product} / {lot} / {when}"
