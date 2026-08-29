from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StoreInventoryConvertWizard(models.TransientModel):
    _name = "five.five.store.inventory.convert.wizard"
    _description = "Convert store inventory from one variant to another"

    store_id = fields.Many2one(
        "five.five.store",
        string="Store",
        required=True,
    )
    from_line = fields.Boolean(default=False)
    store_inventory_id = fields.Many2one(
        "five.five.store.inventory",
        string="From Stock",
        ondelete="cascade",
    )
    source_lot_number = fields.Char(
        related="store_inventory_id.lot_number",
        string="Lot No.",
        readonly=True,
    )
    source_product_variant_id = fields.Many2one(
        "five.five.product.variant",
        related="store_inventory_id.product_variant_id",
        string="From Product",
        readonly=True,
    )
    quantity_on_hand = fields.Float(
        related="store_inventory_id.quantity",
        string="Qty On Hand",
        readonly=True,
        digits=(16, 6),
    )
    weight_on_hand = fields.Float(
        related="store_inventory_id.total_weight",
        string="Weight On Hand (Kg.)",
        readonly=True,
        digits=(16, 6),
    )
    target_product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="To Product",
    )
    convert_qty = fields.Float(string="Convert Qty", digits=(16, 6), default=0.0)
    line_ids = fields.One2many(
        "five.five.store.inventory.convert.wizard.line",
        "wizard_id",
        string="Conversions",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        store_inventory_id = self.env.context.get("default_store_inventory_id")
        if not store_inventory_id:
            return res

        inventory = self.env["five.five.store.inventory"].browse(store_inventory_id).exists()
        if not inventory:
            return res

        res["from_line"] = True
        res["store_id"] = inventory.store_id.id
        res["store_inventory_id"] = inventory.id
        res["convert_qty"] = inventory.quantity
        return res

    @api.onchange("store_inventory_id")
    def _onchange_store_inventory_id(self):
        if (
            self.from_line
            and self.store_inventory_id
            and self.target_product_variant_id == self.store_inventory_id.product_variant_id
        ):
            self.target_product_variant_id = False

    def _iter_conversion_lines(self):
        self.ensure_one()
        if self.from_line:
            yield self.env["five.five.store.inventory.convert.wizard.line"].new(
                {
                    "wizard_id": self.id,
                    "store_inventory_id": self.store_inventory_id.id,
                    "target_product_variant_id": self.target_product_variant_id.id,
                    "convert_qty": self.convert_qty,
                }
            )
        else:
            yield from self.line_ids

    def action_confirm(self):
        self.ensure_one()
        lines = list(self._iter_conversion_lines())
        if not lines:
            raise UserError(_("Please add at least one conversion line."))

        converted = 0
        for line in lines:
            line._validate_line()
            source = line.store_inventory_id
            source._convert_to_variant(line.target_product_variant_id, line.convert_qty)
            converted += 1

        self.store_id.message_post(
            body=_("Reclassified %(count)s store inventory line(s) to another product variant.")
            % {"count": converted}
        )
        return {"type": "ir.actions.act_window_close"}


class StoreInventoryConvertWizardLine(models.TransientModel):
    _name = "five.five.store.inventory.convert.wizard.line"
    _description = "Store inventory convert wizard line"

    wizard_id = fields.Many2one(
        "five.five.store.inventory.convert.wizard",
        required=True,
        ondelete="cascade",
    )
    store_inventory_id = fields.Many2one(
        "five.five.store.inventory",
        string="From Stock",
        required=True,
        ondelete="cascade",
    )
    source_lot_number = fields.Char(
        related="store_inventory_id.lot_number",
        string="Lot No.",
        readonly=True,
    )
    source_product_variant_id = fields.Many2one(
        "five.five.product.variant",
        related="store_inventory_id.product_variant_id",
        string="From Product",
        readonly=True,
    )
    quantity_on_hand = fields.Float(
        related="store_inventory_id.quantity",
        string="Qty On Hand",
        readonly=True,
        digits=(16, 6),
    )
    weight_on_hand = fields.Float(
        related="store_inventory_id.total_weight",
        string="Weight On Hand (Kg.)",
        readonly=True,
        digits=(16, 6),
    )
    target_product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="To Product",
        required=True,
    )
    convert_qty = fields.Float(string="Convert Qty", required=True, digits=(16, 6), default=0.0)

    @api.onchange("store_inventory_id")
    def _onchange_store_inventory_id(self):
        if (
            self.store_inventory_id
            and self.target_product_variant_id == self.store_inventory_id.product_variant_id
        ):
            self.target_product_variant_id = False
            self.convert_qty = self.store_inventory_id.quantity

    def _validate_line(self):
        self.ensure_one()
        source = self.store_inventory_id
        if not source:
            raise UserError(_("Please select store inventory to convert from."))
        if source.store_id != self.wizard_id.store_id:
            raise UserError(_("Selected stock does not belong to this store."))
        if not self.target_product_variant_id:
            raise UserError(_("Please select the target product variant."))
        if float_compare(self.convert_qty or 0.0, 0, precision_digits=6) <= 0:
            raise UserError(_("Convert quantity must be greater than zero."))


class StoreInventoryConvertWizardCostLine(models.TransientModel):
    _name = "five.five.store.inventory.convert.wizard.cost.line"
    _description = "Store inventory convert wizard cost line (legacy)"

    line_id = fields.Many2one(
        "five.five.store.inventory.convert.wizard.line",
        ondelete="cascade",
    )
    cost_name = fields.Char(string="Cost Name")
    cost = fields.Float(string="Cost/Qty (THB)", digits=(16, 2))
    type = fields.Selection(
        selection=[
            ("fixed", "Fixed"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("yearly", "Yearly"),
        ],
        string="Cost Type",
    )
    start_calculate_cost = fields.Date(string="Start Calculate Cost")
