from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class InventoryMovement(models.Model):
    _name = "five.five.inventory.movement"
    _description = "Inventory Movement"
    _order = "id desc"

    name = fields.Char(string="Reference", compute="_compute_name", store=True)
    requisition_id = fields.Many2one(
        "five.five.store.requisition",
        string="Requisition",
        ondelete="cascade",
        index=True,
    )
    requisition_line_id = fields.Many2one(
        "five.five.store.requisition.line",
        string="Requisition Line",
        ondelete="set null",
        index=True,
    )
    warehouse_inventory_id = fields.Many2one(
        "five.five.inventory",
        string="Warehouse Inventory",
        required=True,
        ondelete="restrict",
        index=True,
    )
    warehouse_id = fields.Many2one(
        "five.five.warehouse",
        related="warehouse_inventory_id.warehouse_id",
        store=True,
        readonly=True,
    )
    store_id = fields.Many2one("five.five.store", required=True, index=True)
    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        related="warehouse_inventory_id.product_variant_id",
        store=True,
        readonly=True,
    )
    lot_number = fields.Char(related="warehouse_inventory_id.lot_number", store=True, readonly=True)
    quality_note = fields.Char(related="warehouse_inventory_id.quality_note", readonly=True)
    quantity = fields.Float(string="Quantity", digits=(16, 2), required=True)
    transfer_cost_thb = fields.Float(string="Transfer Cost (THB)", digits=(16, 2))
    state = fields.Selection(
        [
            ("prepared", "Prepared"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        default="prepared",
        required=True,
        index=True,
    )
    prepared_at = fields.Datetime(default=fields.Datetime.now, required=True)
    done_at = fields.Datetime(string="Done At")

    @api.depends("requisition_id.number", "lot_number", "product_variant_id")
    def _compute_name(self):
        for movement in self:
            req = movement.requisition_id.number or "-"
            lot = movement.lot_number or "-"
            product = movement.product_variant_id.display_name or "-"
            movement.name = f"{req} / {product} / {lot}"

    def action_done(self):
        for movement in self:
            if movement.state != "prepared":
                raise UserError(_("Only prepared movements can be completed."))
            movement._apply_transfer()
            movement.write(
                {
                    "state": "done",
                    "done_at": fields.Datetime.now(),
                }
            )
        return True

    def _apply_transfer(self):
        self.ensure_one()
        inventory = self.warehouse_inventory_id
        store = self.store_id

        if float_compare(self.quantity, 0, precision_digits=6) <= 0:
            raise UserError(_("Quantity must be greater than zero."))
        if float_compare(self.quantity, inventory.quantity, precision_digits=6) > 0:
            raise UserError(
                _("Quantity for %(product)s (Lot %(lot)s) exceeds available stock.")
                % {
                    "product": inventory.product_variant_id.display_name,
                    "lot": inventory.lot_number or "-",
                }
            )
        if not (inventory.lot_number or "").strip():
            raise UserError(
                _("Lot number is required for %(product)s.")
                % {"product": inventory.product_variant_id.display_name}
            )

        if not self.transfer_cost_thb and inventory.quantity > 0:
            self.transfer_cost_thb = (inventory.total_cost_thb / inventory.quantity) * self.quantity

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

        if existing:
            new_total_cost = existing.total_cost_thb + transfer_cost
            existing.write(
                {
                    "quantity": existing.quantity + self.quantity,
                    "total_cost_thb": new_total_cost,
                    "cost_summary": ProductCost.format_frozen_store_cost_summary(new_total_cost),
                    "cost_as_of_date": freeze_date,
                }
            )
        else:
            StoreInventory.create(
                {
                    "store_id": store.id,
                    "product_variant_id": inventory.product_variant_id.id,
                    "lot_number": lot_number,
                    "quantity": self.quantity,
                    "quality_note": inventory.quality_note,
                    "purchase_order_id": inventory.purchase_order_id.id,
                    "source_inventory_id": inventory.id,
                    "total_cost_thb": transfer_cost,
                    "cost_summary": ProductCost.format_frozen_store_cost_summary(transfer_cost),
                    "cost_as_of_date": freeze_date,
                }
            )

        inventory._consume_quantity(self.quantity)
