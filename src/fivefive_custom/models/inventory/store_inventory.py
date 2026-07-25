from odoo import api, fields, models


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
