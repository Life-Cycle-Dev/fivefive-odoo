from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang
from odoo.tools.float_utils import float_compare, float_is_zero


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
    supplier_credit_amount_usd = fields.Float(
        string="Supplier Credit (USD)",
        digits=(16, 2),
        help="Optional credit for the supplier when delivered quantity/value is less than paid. "
        "This amount can be applied as a discount on the supplier's next PO.",
    )
    supplier_credit_amount_thb = fields.Float(
        string="Supplier Credit (THB)",
        compute="_compute_supplier_credit_amount_thb",
        digits=(16, 2),
    )
    max_supplier_credit_usd = fields.Float(
        string="Max Supplier Credit (USD)",
        compute="_compute_max_supplier_credit_usd",
        digits=(16, 2),
    )

    @api.depends("purchase_order_id.amount_paid_usd")
    def _compute_max_supplier_credit_usd(self):
        for wizard in self:
            wizard.max_supplier_credit_usd = wizard.purchase_order_id.amount_paid_usd if wizard.purchase_order_id else 0.0

    @api.depends("supplier_credit_amount_usd", "purchase_order_id.exchange_rate_thb_per_usd", "purchase_order_id.amount_recorded_usd", "purchase_order_id.amount_recorded_thb")
    def _compute_supplier_credit_amount_thb(self):
        for wizard in self:
            po = wizard.purchase_order_id
            amount_usd = wizard.supplier_credit_amount_usd or 0.0
            if not po or float_is_zero(amount_usd, precision_digits=2):
                wizard.supplier_credit_amount_thb = 0.0
                continue
            if po.exchange_rate_thb_per_usd:
                wizard.supplier_credit_amount_thb = amount_usd * po.exchange_rate_thb_per_usd
            elif po.amount_recorded_usd:
                wizard.supplier_credit_amount_thb = amount_usd * (po.amount_recorded_thb / po.amount_recorded_usd)
            else:
                wizard.supplier_credit_amount_thb = 0.0

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

        close_date = self.as_of_date or fields.Date.context_today(self)
        Inventory = self.env["five.five.inventory"]
        inventory_vals = []
        for line in self.line_ids:
            convert = line.product_convert_id
            if not convert:
                continue

            convert_lot = (convert.lot_number or "").strip()
            if not convert_lot:
                raise UserError(
                    _("Lot number is required for %(product)s.")
                    % {"product": convert.product_variant_id.display_name}
                )

            cil = convert.commercial_invoice_line_id
            totals = ProductCost.compute_convert_cost_totals(convert, as_of_date=self.as_of_date)
            inventory_vals.append(
                {
                    "warehouse_id": po.warehouse_id.id,
                    "product_variant_id": convert.product_variant_id.id,
                    "quantity": convert.quantity,
                    "quality_note": convert.quality_note,
                    "quality_image": convert.quality_image,
                    "lot_number": convert_lot,
                    "item_number": convert.item_number,
                    "container_number": convert.container_number or po.shipment_container_number,
                    "brand_id": convert.brand_id.id if convert.brand_id else False,
                    "description_id": convert.description_id.id if convert.description_id else False,
                    "weight_per_qty": convert.weight_per_qty or (cil.weight_per_qty if cil else 0.0),
                    "total_weight": convert.total_weight or (cil.total_weight if cil else 0.0),
                    "purchase_order_id": po.id,
                    "product_convert_id": convert.id,
                    "cost_summary": ProductCost.format_cost_amount_summary(totals),
                    "total_cost_thb": line.total_cost_thb,
                    "cost_as_of_date": self.as_of_date,
                    "po_closed_date": close_date,
                }
            )

        if not inventory_vals:
            raise UserError(_("No converted products found to create inventory."))

        credit_amount_usd = self.supplier_credit_amount_usd or 0.0
        if float_compare(credit_amount_usd, 0, precision_digits=2) < 0:
            raise UserError(_("Supplier credit amount cannot be negative."))
        if float_compare(credit_amount_usd, po.amount_paid_usd, precision_digits=2) > 0:
            raise UserError(_("Supplier credit amount cannot exceed the paid amount on this PO."))

        self.env["five.five.inventory"].create(inventory_vals)
        if float_compare(credit_amount_usd, 0, precision_digits=2) > 0:
            self.env["five.five.supplier.credit"].create(
                {
                    "supplier_id": po.supplier_id.id,
                    "source_purchase_order_id": po.id,
                    "amount_usd": credit_amount_usd,
                    "amount_thb": self.supplier_credit_amount_thb,
                    "remaining_usd": credit_amount_usd,
                    "remaining_thb": self.supplier_credit_amount_thb,
                }
            )
        po.state = "closed"
        close_message = _(
            "Closed PO and created %(count)s inventory record(s) at warehouse %(warehouse)s. "
            "Total cost: %(total)s THB as of %(date)s."
        ) % {
            "count": len(inventory_vals),
            "warehouse": po.warehouse_id.display_name,
            "total": formatLang(self.env, self.total_cost_thb, digits=2),
            "date": self.as_of_date.strftime("%d/%m/%Y") if self.as_of_date else "-",
        }
        if float_compare(credit_amount_usd, 0, precision_digits=2) > 0:
            close_message += "\n" + _(
                "Created supplier credit %(amount_usd)s USD (%(amount_thb)s THB) for %(supplier)s."
            ) % {
                "amount_usd": formatLang(self.env, credit_amount_usd, digits=2),
                "amount_thb": formatLang(self.env, self.supplier_credit_amount_thb, digits=2),
                "supplier": po.supplier_id.display_name,
            }
        po.message_post(body=close_message)
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
    lot_number = fields.Char(
        related="product_convert_id.lot_number",
        readonly=True,
    )
    item_number = fields.Char(
        related="product_convert_id.item_number",
        readonly=True,
    )
    container_number = fields.Char(
        related="product_convert_id.container_number",
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
