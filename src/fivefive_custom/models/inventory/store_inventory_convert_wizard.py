from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero
from odoo.tools.misc import formatLang


class StoreInventoryConvertWizard(models.TransientModel):
    _name = "five.five.store.inventory.convert.wizard"
    _description = "Convert store inventory from one variant to another"

    store_id = fields.Many2one(
        "five.five.store",
        string="Store",
        required=True,
    )
    line_ids = fields.One2many(
        "five.five.store.inventory.convert.wizard.line",
        "wizard_id",
        string="Conversions",
    )

    def action_confirm(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Please add at least one conversion line."))

        StoreInventory = self.env["five.five.store.inventory"]
        converted = 0
        for line in self.line_ids:
            line._validate_line()
            source = line.store_inventory_id
            convert_qty = line.convert_qty
            old_qty = source.quantity or 0.0
            old_weight = source.total_weight or source._weight_for_qty(old_qty)
            old_cost = source.total_cost_thb or 0.0
            transfer_cost = old_cost * (convert_qty / old_qty) if old_qty else 0.0
            transfer_weight = source._weight_for_qty(convert_qty)
            new_source_qty = old_qty - convert_qty
            new_source_weight = old_weight - transfer_weight
            new_source_cost = old_cost - transfer_cost

            target_lot = (line.target_lot_number or "").strip()
            existing_target = StoreInventory.search(
                [
                    ("store_id", "=", self.store_id.id),
                    ("lot_number", "=", target_lot),
                ],
                limit=1,
            )
            if existing_target:
                if existing_target.product_variant_id != line.target_product_variant_id:
                    raise ValidationError(
                        _(
                            "Lot %(lot)s already exists in store %(store)s for another product "
                            "(%(product)s)."
                        )
                        % {
                            "lot": target_lot,
                            "store": self.store_id.display_name,
                            "product": existing_target.product_variant_id.display_name,
                        }
                    )
                existing_target._apply_stock_update(
                    existing_target.quantity + convert_qty,
                    existing_target.total_cost_thb + transfer_cost,
                    (existing_target.total_weight or 0.0) + transfer_weight,
                )
            else:
                StoreInventory.create(
                    {
                        "store_id": self.store_id.id,
                        "product_variant_id": line.target_product_variant_id.id,
                        "lot_number": target_lot,
                        "quantity": convert_qty,
                        "quality_note": source.quality_note,
                        "brand_id": source.brand_id.id if source.brand_id else False,
                        "description_id": source.description_id.id if source.description_id else False,
                        "weight_per_qty": source.weight_per_qty,
                        "total_weight": transfer_weight,
                        "purchase_order_id": source.purchase_order_id.id,
                        "source_inventory_id": source.source_inventory_id.id,
                        "total_cost_thb": transfer_cost,
                        "cost_summary": self.env["five.five.product.cost"].format_frozen_store_cost_summary(
                            transfer_cost
                        ),
                        "cost_as_of_date": source.cost_as_of_date,
                    }
                )

            if float_is_zero(new_source_qty, precision_digits=6):
                source.unlink()
            else:
                source._apply_stock_update(new_source_qty, new_source_cost, new_source_weight)
            converted += 1

        self.store_id.message_post(
            body=_("Converted %(count)s store inventory line(s) to new product variant(s).")
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
    target_lot_number = fields.Char(string="Target Lot No.", required=True)

    @api.onchange("store_inventory_id")
    def _onchange_store_inventory_id(self):
        if (
            self.store_inventory_id
            and self.target_product_variant_id == self.store_inventory_id.product_variant_id
        ):
            self.target_product_variant_id = False

    def _validate_line(self):
        self.ensure_one()
        source = self.store_inventory_id
        if not source:
            raise UserError(_("Please select store inventory to convert from."))
        if source.store_id != self.wizard_id.store_id:
            raise UserError(_("Selected stock does not belong to this store."))
        if not self.target_product_variant_id:
            raise UserError(_("Please select the target product variant."))
        if self.target_product_variant_id == source.product_variant_id:
            raise UserError(
                _("Target product must be different from source product (%(product)s).")
                % {"product": source.product_variant_id.display_name}
            )
        convert_qty = self.convert_qty or 0.0
        if float_compare(convert_qty, 0, precision_digits=6) <= 0:
            raise UserError(_("Convert quantity must be greater than zero."))
        if float_compare(convert_qty, source.quantity or 0.0, precision_digits=6) > 0:
            raise UserError(
                _(
                    "Convert quantity (%(convert)s) exceeds available quantity (%(available)s) "
                    "for %(product)s (Lot %(lot)s)."
                )
                % {
                    "convert": formatLang(self.env, convert_qty, digits=2),
                    "available": formatLang(self.env, source.quantity, digits=2),
                    "product": source.product_variant_id.display_name,
                    "lot": source.lot_number or "-",
                }
            )
        target_lot = (self.target_lot_number or "").strip()
        if not target_lot:
            raise UserError(_("Target lot number is required."))
        if target_lot == (source.lot_number or "").strip():
            raise UserError(_("Target lot number must be different from the source lot number."))


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
