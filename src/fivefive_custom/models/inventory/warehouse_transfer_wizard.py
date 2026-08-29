from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class WarehouseTransferWizard(models.TransientModel):
    _name = "five.five.warehouse.transfer.wizard"
    _description = "Transfer inventory from warehouse to store"

    warehouse_id = fields.Many2one(
        "five.five.warehouse",
        string="Warehouse",
        domain=[("active", "=", True)],
    )
    store_id = fields.Many2one(
        "five.five.store",
        string="Store",
        required=True,
        domain=[("active", "=", True)],
    )
    lock_store = fields.Boolean(default=False)
    lock_warehouse = fields.Boolean(default=False)
    available_product_variant_ids = fields.Many2many(
        "five.five.product.variant",
        compute="_compute_available_product_variant_ids",
    )
    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="Product Variant",
    )
    line_ids = fields.One2many(
        "five.five.warehouse.transfer.wizard.line",
        "wizard_id",
        string="Transfer Lines",
    )
    total_transfer_cost_thb = fields.Float(
        string="Total Transfer Cost (THB)",
        compute="_compute_total_transfer_cost_thb",
        digits=(16, 2),
    )
    line_count = fields.Integer(
        string="Line Count",
        compute="_compute_total_transfer_cost_thb",
    )

    @api.depends("line_ids.transfer_cost_thb", "line_ids.quantity")
    def _compute_total_transfer_cost_thb(self):
        for wizard in self:
            active_lines = wizard.line_ids.filtered(lambda line: line.quantity > 0)
            wizard.total_transfer_cost_thb = sum(active_lines.mapped("transfer_cost_thb"))
            wizard.line_count = len(active_lines)

    @api.depends("warehouse_id")
    def _compute_available_product_variant_ids(self):
        Inventory = self.env["five.five.inventory"]
        for wizard in self:
            if wizard.warehouse_id:
                inventories = Inventory.search(
                    [
                        ("warehouse_id", "=", wizard.warehouse_id.id),
                        ("quantity", ">", 0),
                    ]
                )
                wizard.available_product_variant_ids = inventories.mapped("product_variant_id")
            else:
                wizard.available_product_variant_ids = False

    def _load_lines_for_product(self):
        self.ensure_one()
        self.line_ids = [(5, 0, 0)]
        if not self.warehouse_id or not self.product_variant_id:
            return
        inventories = self.env["five.five.inventory"].search(
            [
                ("warehouse_id", "=", self.warehouse_id.id),
                ("product_variant_id", "=", self.product_variant_id.id),
                ("quantity", ">", 0),
            ],
            order="lot_number, id",
        )
        self.line_ids = [
            (0, 0, {"inventory_id": inventory.id, "quantity": 0.0})
            for inventory in inventories
        ]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        inventory_ids = list(self.env.context.get("default_inventory_ids") or [])
        if not inventory_ids and self.env.context.get("active_model") == "five.five.inventory":
            inventory_ids = list(self.env.context.get("active_ids") or [])
        if not inventory_ids and self.env.context.get("default_inventory_id"):
            inventory_ids = [self.env.context["default_inventory_id"]]

        store_id = res.get("store_id") or self.env.context.get("default_store_id")
        if store_id:
            res["store_id"] = store_id
            res["lock_store"] = True
        if self.env.context.get("default_warehouse_id"):
            res["lock_warehouse"] = True

        product_variant_id = res.get("product_variant_id") or self.env.context.get(
            "default_product_variant_id"
        )

        if inventory_ids:
            inventories = self.env["five.five.inventory"].browse(inventory_ids).exists()
            if inventories:
                res["warehouse_id"] = inventories[0].warehouse_id.id
                res["lock_warehouse"] = True
                variants = inventories.mapped("product_variant_id")
                if len(variants) == 1:
                    product_variant_id = variants.id
        elif product_variant_id and res.get("warehouse_id"):
            res["lock_warehouse"] = bool(self.env.context.get("default_warehouse_id"))

        if product_variant_id:
            res["product_variant_id"] = product_variant_id

        warehouse_id = res.get("warehouse_id") or self.env.context.get("default_warehouse_id")
        if product_variant_id and warehouse_id:
            all_inventories = self.env["five.five.inventory"].search(
                [
                    ("warehouse_id", "=", warehouse_id),
                    ("product_variant_id", "=", product_variant_id),
                    ("quantity", ">", 0),
                ],
                order="lot_number, id",
            )
            if all_inventories:
                res["line_ids"] = [
                    (0, 0, {"inventory_id": inventory.id, "quantity": 0.0})
                    for inventory in all_inventories
                ]
        return res

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        if self.lock_warehouse:
            return
        self.product_variant_id = False
        self.line_ids = [(5, 0, 0)]

    @api.onchange("product_variant_id")
    def _onchange_product_variant_id(self):
        self._load_lines_for_product()

    def _action_after_transfer(self):
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_confirm(self):
        self.ensure_one()
        if not self.warehouse_id:
            raise UserError(_("Please select a warehouse."))
        if not self.store_id:
            raise UserError(_("Please select a store."))
        if not self.product_variant_id:
            raise UserError(_("Please select a product variant."))

        self.line_ids.filtered(lambda line: not line.inventory_id).unlink()

        if not self.line_ids.filtered("inventory_id"):
            raise UserError(_("No available inventory found for the selected product."))

        self.env.flush_all()
        lines_to_transfer = self.line_ids.filtered(
            lambda line: line.inventory_id and line.quantity > 0
        )
        if not lines_to_transfer:
            raise UserError(_("Please enter transfer quantity for at least one item."))

        transfer_details = []
        total_cost = 0.0
        for line in lines_to_transfer:
            transfer_cost = line._apply_transfer()
            total_cost += transfer_cost
            transfer_details.append(
                _("- %(product)s (Lot %(lot)s): %(qty)s qty, %(cost)s THB")
                % {
                    "product": line.product_variant_id.display_name,
                    "lot": line.lot_number,
                    "qty": line.quantity,
                    "cost": f"{transfer_cost:,.2f}",
                }
            )

        warehouse = self.warehouse_id
        if warehouse:
            warehouse.message_post(
                body=_(
                    "Transferred %(count)s item(s) to store %(store)s. "
                    "Total transfer cost: %(total)s THB\n%(details)s"
                )
                % {
                    "count": len(lines_to_transfer),
                    "store": self.store_id.display_name,
                    "total": f"{total_cost:,.2f}",
                    "details": "\n".join(transfer_details),
                }
            )
        self.store_id.message_post(
            body=_(
                "Received %(count)s item(s) from warehouse %(warehouse)s. "
                "Total transfer cost: %(total)s THB\n%(details)s"
            )
            % {
                "count": len(lines_to_transfer),
                "warehouse": warehouse.display_name if warehouse else "-",
                "total": f"{total_cost:,.2f}",
                "details": "\n".join(transfer_details),
            }
        )
        return self._action_after_transfer()


class WarehouseTransferWizardLine(models.TransientModel):
    _name = "five.five.warehouse.transfer.wizard.line"
    _description = "Transfer inventory wizard line"

    wizard_id = fields.Many2one(
        "five.five.warehouse.transfer.wizard",
        required=True,
        ondelete="cascade",
    )
    inventory_id = fields.Many2one(
        "five.five.inventory",
        string="Warehouse Inventory",
        readonly=True,
    )
    product_variant_id = fields.Many2one(
        related="inventory_id.product_variant_id",
        readonly=True,
    )
    lot_number = fields.Char(related="inventory_id.lot_number", readonly=True)
    quality_note = fields.Char(related="inventory_id.quality_note", readonly=True)
    available_quantity = fields.Float(related="inventory_id.quantity", readonly=True)
    cost_summary = fields.Char(related="inventory_id.cost_summary", readonly=True)
    cost_as_of_date = fields.Date(related="inventory_id.cost_as_of_date", readonly=True)
    unit_cost_thb = fields.Float(
        string="Cost per Unit (THB)",
        compute="_compute_unit_cost_thb",
        digits=(16, 2),
        readonly=True,
    )
    total_lot_cost_thb = fields.Float(
        string="Total Lot Cost (THB)",
        related="inventory_id.total_cost_thb",
        readonly=True,
    )
    quantity = fields.Float(string="Transfer Quantity", default=0.0)
    transfer_cost_thb = fields.Float(
        string="Transfer Cost (THB)",
        compute="_compute_transfer_cost_thb",
        digits=(16, 2),
        readonly=True,
    )
    frozen_cost_summary = fields.Char(
        string="Store Cost Summary",
        compute="_compute_frozen_cost_summary",
        readonly=True,
    )

    @api.depends("transfer_cost_thb")
    def _compute_frozen_cost_summary(self):
        ProductCost = self.env["five.five.product.cost"]
        for line in self:
            line.frozen_cost_summary = ProductCost.format_frozen_store_cost_summary(
                line.transfer_cost_thb
            )

    @api.depends("inventory_id.total_cost_thb", "inventory_id.quantity")
    def _compute_unit_cost_thb(self):
        for line in self:
            inventory = line.inventory_id
            if inventory and inventory.quantity > 0:
                line.unit_cost_thb = inventory.total_cost_thb / inventory.quantity
            else:
                line.unit_cost_thb = 0.0

    @api.depends("quantity", "inventory_id.total_cost_thb", "inventory_id.quantity")
    def _compute_transfer_cost_thb(self):
        for line in self:
            inventory = line.inventory_id
            if inventory and inventory.quantity > 0 and line.quantity > 0:
                line.transfer_cost_thb = (
                    inventory.total_cost_thb / inventory.quantity
                ) * line.quantity
            else:
                line.transfer_cost_thb = 0.0

    @api.onchange("inventory_id")
    def _onchange_inventory_id(self):
        if self.inventory_id:
            self.quantity = 0.0

    def _apply_transfer(self):
        self.ensure_one()
        inventory = self.inventory_id
        store = self.wizard_id.store_id

        if not inventory:
            raise UserError(_("Warehouse inventory not found."))
        if self.quantity <= 0:
            raise UserError(
                _("Transfer quantity must be greater than 0 for %(product)s.")
                % {"product": inventory.product_variant_id.display_name}
            )
        if float_compare(self.quantity, inventory.quantity, precision_digits=6) > 0:
            raise UserError(
                _("Transfer quantity for %(product)s (Lot %(lot)s) cannot exceed available quantity.")
                % {
                    "product": inventory.product_variant_id.display_name,
                    "lot": inventory.lot_number or "-",
                }
            )
        if not (inventory.lot_number or "").strip():
            raise UserError(
                _("Lot number is required to transfer %(product)s.")
                % {"product": inventory.product_variant_id.display_name}
            )

        transfer_cost = self.transfer_cost_thb
        freeze_date = fields.Date.context_today(self)
        lot_number = inventory.lot_number.strip()
        ProductCost = self.env["five.five.product.cost"]
        StoreInventory = self.env["five.five.store.inventory"]
        existing = StoreInventory.search(
            [
                ("store_id", "=", store.id),
                ("lot_number", "=", lot_number),
            ],
            limit=1,
        )

        store_vals = {
            "product_variant_id": inventory.product_variant_id.id,
            "quantity": self.quantity,
            "quality_note": inventory.quality_note,
            "brand_id": inventory.brand_id.id if inventory.brand_id else False,
            "description_id": inventory.description_id.id if inventory.description_id else False,
            "weight_per_qty": inventory.weight_per_qty,
            "total_weight": inventory._weight_for_qty(self.quantity),
            "purchase_order_id": inventory.purchase_order_id.id,
            "source_inventory_id": inventory.id,
            "total_cost_thb": transfer_cost,
            "cost_as_of_date": freeze_date,
        }

        if existing:
            new_total_cost = existing.total_cost_thb + transfer_cost
            existing._apply_stock_update(
                existing.quantity + self.quantity,
                new_total_cost,
                (existing.total_weight or 0.0) + store_vals["total_weight"],
            )
            existing.write({"cost_as_of_date": freeze_date})
        else:
            StoreInventory.create(
                {
                    **store_vals,
                    "store_id": store.id,
                    "lot_number": lot_number,
                    "cost_summary": ProductCost.format_frozen_store_cost_summary(transfer_cost),
                }
            )

        inventory._consume_quantity(self.quantity)
        return transfer_cost
