from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class PurchaseOrderCloseWizard(models.TransientModel):
    _name = "five.five.purchase.order.close.wizard"
    _description = "Purchase order close wizard"

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        required=True,
        readonly=True,
    )
    warehouse_id = fields.Many2one(
        "five.five.warehouse",
        string="Warehouse",
        related="purchase_order_id.warehouse_id",
        readonly=True,
    )
    lot_number = fields.Char(string="Lot Number")
    as_of_date = fields.Date(
        string="Cost As Of",
        default=fields.Date.context_today,
        readonly=True,
    )
    line_ids = fields.One2many(
        "five.five.purchase.order.close.wizard.line",
        "wizard_id",
        string="Converted Products",
    )
    total_cost_thb = fields.Float(
        string="Total Cost (THB)",
        compute="_compute_total_cost_thb",
        digits=(16, 2),
    )
    total_cost_thb_display = fields.Char(
        string="Total Cost Summary",
        compute="_compute_total_cost_thb",
    )

    @api.depends("line_ids.total_cost_thb", "as_of_date")
    def _compute_total_cost_thb(self):
        for wizard in self:
            total = sum(wizard.line_ids.mapped("total_cost_thb"))
            wizard.total_cost_thb = total
            formatted = formatLang(wizard.env, total, digits=2)
            wizard.total_cost_thb_display = _(
                "Total Cost: %(amount)s THB (as of %(date)s)"
            ) % {
                "amount": formatted,
                "date": wizard.as_of_date.strftime("%d/%m/%Y") if wizard.as_of_date else "-",
            }

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        po_id = res.get("purchase_order_id") or self.env.context.get("default_purchase_order_id")
        if not po_id:
            return res

        po = self.env["five.five.purchase.order"].browse(po_id)
        res["purchase_order_id"] = po.id
        res["lot_number"] = po.lot_number or ""
        res["line_ids"] = [
            (0, 0, {"product_convert_id": convert.id})
            for convert in po.converted_product_ids
        ]
        return res

    def action_confirm(self):
        self.ensure_one()
        po = self.purchase_order_id
        ProductCost = self.env["five.five.product.cost"]

        if not po:
            raise UserError(_("Purchase Order not found."))
        if po.state != "clearing":
            raise UserError(_("Only POs in Clearing status can be closed."))
        if not po.warehouse_id:
            raise UserError(_("Warehouse is required before closing this PO."))
        if not self.line_ids:
            raise UserError(_("Please convert products before closing this PO."))

        lot_number = (self.lot_number or "").strip()
        if not lot_number:
            raise UserError(_("Lot number is required before closing this PO."))

        Inventory = self.env["five.five.inventory"]
        inventory_vals = []
        for line in self.line_ids:
            convert = line.product_convert_id
            if not convert:
                continue

            duplicate = Inventory.search_count(
                [
                    ("warehouse_id", "=", po.warehouse_id.id),
                    ("lot_number", "=", lot_number),
                    ("product_variant_id", "=", convert.product_variant_id.id),
                ]
            )
            if duplicate:
                raise UserError(
                    _(
                        "Lot number %(lot)s for product %(product)s already exists in warehouse %(warehouse)s."
                    )
                    % {
                        "lot": lot_number,
                        "product": convert.product_variant_id.display_name,
                        "warehouse": po.warehouse_id.display_name,
                    }
                )

            totals = ProductCost.compute_convert_cost_totals(convert, as_of_date=self.as_of_date)
            inventory_vals.append(
                {
                    "warehouse_id": po.warehouse_id.id,
                    "product_variant_id": convert.product_variant_id.id,
                    "quantity": convert.quantity,
                    "quality_note": convert.quality_note,
                    "lot_number": lot_number,
                    "purchase_order_id": po.id,
                    "product_convert_id": convert.id,
                    "cost_summary": ProductCost.format_cost_amount_summary(totals),
                    "total_cost_thb": line.total_cost_thb,
                    "cost_as_of_date": self.as_of_date,
                }
            )

        if not inventory_vals:
            raise UserError(_("No converted products found to create inventory."))

        if po.lot_number != lot_number:
            po.write({"lot_number": lot_number})

        self.env["five.five.inventory"].create(inventory_vals)
        po.state = "closed"
        po.message_post(
            body=_(
                "Closed PO and created %(count)s inventory record(s) at warehouse %(warehouse)s "
                "with lot number %(lot)s. Total cost: %(total)s THB as of %(date)s."
            )
            % {
                "count": len(inventory_vals),
                "warehouse": po.warehouse_id.display_name,
                "lot": lot_number,
                "total": formatLang(self.env, self.total_cost_thb, digits=2),
                "date": self.as_of_date.strftime("%d/%m/%Y") if self.as_of_date else "-",
            }
        )
        return {"type": "ir.actions.act_window_close"}


class PurchaseOrderCloseWizardLine(models.TransientModel):
    _name = "five.five.purchase.order.close.wizard.line"
    _description = "Purchase order close wizard line"

    wizard_id = fields.Many2one(
        "five.five.purchase.order.close.wizard",
        required=True,
        ondelete="cascade",
    )
    product_convert_id = fields.Many2one(
        "five.five.product.convert",
        string="Converted Product",
        required=True,
        readonly=True,
    )
    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        related="product_convert_id.product_variant_id",
        readonly=True,
    )
    quantity = fields.Float(
        related="product_convert_id.quantity",
        readonly=True,
    )
    quality_note = fields.Char(
        related="product_convert_id.quality_note",
        readonly=True,
    )
    cost_summary = fields.Char(
        string="Cost Summary",
        compute="_compute_cost_fields",
    )
    total_cost_thb = fields.Float(
        string="Total Cost (THB)",
        compute="_compute_cost_fields",
        digits=(16, 2),
    )

    @api.depends(
        "product_convert_id",
        "product_convert_id.product_cost_ids",
        "product_convert_id.product_cost_ids.cost",
        "product_convert_id.product_cost_ids.type",
        "product_convert_id.product_cost_ids.start_calculate_cost",
        "product_convert_id.quantity",
        "wizard_id.as_of_date",
    )
    def _compute_cost_fields(self):
        ProductCost = self.env["five.five.product.cost"]
        for line in self:
            convert = line.product_convert_id
            as_of_date = line.wizard_id.as_of_date
            if not convert:
                line.cost_summary = _("No costs")
                line.total_cost_thb = 0.0
                continue
            totals = ProductCost.compute_convert_cost_totals(convert, as_of_date=as_of_date)
            line.cost_summary = ProductCost.format_cost_amount_summary(totals)
            line.total_cost_thb = sum(totals.values())
