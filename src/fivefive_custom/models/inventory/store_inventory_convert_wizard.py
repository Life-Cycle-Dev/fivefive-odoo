from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare
from odoo.tools.misc import formatLang


class StoreInventoryConvertWizard(models.TransientModel):
    _name = "five.five.store.inventory.convert.wizard"
    _description = "Convert product into store inventory"

    store_id = fields.Many2one(
        "five.five.store",
        string="Store",
        required=True,
    )
    as_of_date = fields.Date(
        string="Cost As Of",
        default=fields.Date.context_today,
        required=True,
    )
    line_ids = fields.One2many(
        "five.five.store.inventory.convert.wizard.line",
        "wizard_id",
        string="Products",
    )
    total_cost_thb = fields.Float(
        string="Total Cost (THB)",
        compute="_compute_total_cost_thb",
        digits=(16, 2),
    )

    @api.depends("line_ids.total_cost_thb")
    def _compute_total_cost_thb(self):
        for wizard in self:
            wizard.total_cost_thb = sum(wizard.line_ids.mapped("total_cost_thb"))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        store_id = res.get("store_id") or self.env.context.get("default_store_id")
        if store_id:
            res["store_id"] = store_id
        if "line_ids" in fields_list and not res.get("line_ids"):
            res["line_ids"] = [
                (
                    0,
                    0,
                    {
                        "cost_line_ids": [
                            (0, 0, {"cost_name": "Product Cost", "cost": 0.0, "type": "fixed"}),
                        ],
                    },
                )
            ]
        return res

    def action_confirm(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Please add at least one product line."))

        ProductConvert = self.env["five.five.product.convert"]
        ProductCost = self.env["five.five.product.cost"]
        StoreInventory = self.env["five.five.store.inventory"]
        created = self.env["five.five.store.inventory"]

        for line in self.line_ids:
            line._validate_cost_lines()
            if float_compare(line.quantity, 0, precision_digits=6) <= 0:
                raise UserError(_("Quantity must be greater than zero."))

            lot_number = (line.lot_number or "").strip()
            if not lot_number:
                raise UserError(_("Lot number is required for %(product)s.") % {"product": line.product_variant_id.display_name})

            duplicate = StoreInventory.search_count(
                [
                    ("store_id", "=", self.store_id.id),
                    ("lot_number", "=", lot_number),
                ]
            )
            if duplicate:
                raise ValidationError(
                    _("Lot number %(lot)s already exists in store %(store)s.")
                    % {"lot": lot_number, "store": self.store_id.display_name}
                )

            convert = ProductConvert.create(
                {
                    "is_manual_receipt": True,
                    "product_variant_id": line.product_variant_id.id,
                    "quantity": line.quantity,
                    "quality_note": line.quality_note or "-",
                    "quality_image": line.quality_image,
                    "item_number": line.item_number,
                    "container_number": line.container_number,
                    "lot_number": lot_number,
                    "brand_id": line.brand_id.id if line.brand_id else False,
                    "description_id": line.description_id.id if line.description_id else False,
                    "weight_per_qty": line.weight_per_qty,
                }
            )
            for cost_line in line.cost_line_ids:
                ProductCost.create(
                    {
                        "product_convert_id": convert.id,
                        "cost_name": cost_line.cost_name.strip(),
                        "cost": cost_line.cost,
                        "type": cost_line.type,
                        "start_calculate_cost": cost_line.start_calculate_cost,
                    }
                )

            totals = ProductCost.compute_convert_cost_totals(convert, as_of_date=self.as_of_date)
            total_cost = sum(totals.values())
            inventory = StoreInventory.create(
                {
                    "store_id": self.store_id.id,
                    "product_variant_id": line.product_variant_id.id,
                    "quantity": line.quantity,
                    "quality_note": line.quality_note or "-",
                    "lot_number": lot_number,
                    "brand_id": line.brand_id.id if line.brand_id else False,
                    "description_id": line.description_id.id if line.description_id else False,
                    "weight_per_qty": line.weight_per_qty,
                    "total_weight": (line.quantity or 0.0) * (line.weight_per_qty or 0.0),
                    "total_cost_thb": total_cost,
                    "cost_summary": ProductCost.format_frozen_store_cost_summary(total_cost),
                    "cost_as_of_date": self.as_of_date,
                }
            )
            created |= inventory

        self.store_id.message_post(
            body=_(
                "Converted %(count)s product(s) into store inventory. "
                "Total cost: %(total)s THB as of %(date)s."
            )
            % {
                "count": len(created),
                "total": formatLang(self.env, self.total_cost_thb, digits=2),
                "date": self.as_of_date.strftime("%d/%m/%Y") if self.as_of_date else "-",
            }
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
    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="Product Variant",
        required=True,
    )
    quantity = fields.Float(string="Quantity", required=True, digits=(16, 6), default=1.0)
    lot_number = fields.Char(string="Lot Number", required=True)
    item_number = fields.Char(string="Item Number")
    container_number = fields.Char(string="Container No.")
    brand_id = fields.Many2one("five.five.product.brand", string="Brand")
    description_id = fields.Many2one("five.five.product.description", string="Description")
    weight_per_qty = fields.Float(string="Weight per Qty")
    quality_note = fields.Char(string="Quality Note")
    quality_image = fields.Image(string="Quality Image", max_width=1920, max_height=1920)
    cost_line_ids = fields.One2many(
        "five.five.store.inventory.convert.wizard.cost.line",
        "line_id",
        string="Costs",
        default=lambda self: [
            (0, 0, {"cost_name": "Product Cost", "cost": 0.0, "type": "fixed"}),
        ],
    )
    cost_summary = fields.Char(string="Cost Summary", compute="_compute_cost_fields")
    total_cost_thb = fields.Float(
        string="Total Cost (THB)",
        compute="_compute_cost_fields",
        digits=(16, 2),
    )

    @api.depends(
        "cost_line_ids.cost",
        "cost_line_ids.type",
        "cost_line_ids.start_calculate_cost",
        "quantity",
        "wizard_id.as_of_date",
    )
    def _compute_cost_fields(self):
        ProductCost = self.env["five.five.product.cost"]
        for line in self:
            totals = line._compute_cost_totals()
            line.cost_summary = ProductCost.format_cost_amount_summary(totals)
            line.total_cost_thb = sum(totals.values())

    def _compute_cost_totals(self):
        from ..product.product_cost import COST_TYPE_ORDER

        ProductCost = self.env["five.five.product.cost"]
        as_of_date = self.wizard_id.as_of_date or fields.Date.context_today(self)
        totals = {key: 0.0 for key in COST_TYPE_ORDER}
        quantity = self.quantity or 0.0
        for cost_line in self.cost_line_ids:
            if cost_line.type not in totals:
                continue
            periods = ProductCost._interval_period_count(
                cost_line.start_calculate_cost,
                as_of_date,
                cost_line.type,
            )
            totals[cost_line.type] += (cost_line.cost or 0.0) * quantity * periods
        return totals

    def _validate_cost_lines(self):
        self.ensure_one()
        if not self.cost_line_ids:
            raise UserError(
                _("Please add at least one cost line for %(product)s.")
                % {"product": self.product_variant_id.display_name}
            )
        for cost_line in self.cost_line_ids:
            cost_line._validate_values()


class StoreInventoryConvertWizardCostLine(models.TransientModel):
    _name = "five.five.store.inventory.convert.wizard.cost.line"
    _description = "Store inventory convert wizard cost line"

    line_id = fields.Many2one(
        "five.five.store.inventory.convert.wizard.line",
        required=True,
        ondelete="cascade",
    )
    cost_name = fields.Char(string="Cost Name", required=True)
    cost = fields.Float(string="Cost/Qty (THB)", required=True, digits=(16, 2))
    type = fields.Selection(
        selection=[
            ("fixed", "Fixed"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("yearly", "Yearly"),
        ],
        string="Cost Type",
        required=True,
        default="fixed",
    )
    start_calculate_cost = fields.Date(string="Start Calculate Cost")

    def _validate_values(self):
        self.ensure_one()
        if not (self.cost_name or "").strip():
            raise UserError(_("Cost name is required."))
        if self.cost is None or self.cost < 0:
            raise UserError(_("Cost must be zero or greater."))
        if self.type in ("daily", "weekly", "monthly", "yearly") and not self.start_calculate_cost:
            raise UserError(_("Start calculate cost is required for interval cost types."))
