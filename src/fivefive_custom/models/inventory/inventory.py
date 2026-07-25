from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Inventory(models.Model):
    _name = "five.five.inventory"
    _description = "Inventory"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="Product Variant",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        "five.five.warehouse",
        string="Warehouse",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    lot_number = fields.Char(string="Lot Number", tracking=True)
    quantity = fields.Float(string="Quantity", tracking=True)
    quality_note = fields.Char(string="Quality Note", tracking=True)
    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        ondelete="set null",
        index=True,
        readonly=True,
        tracking=True,
    )
    product_convert_id = fields.Many2one(
        "five.five.product.convert",
        string="Converted Product",
        ondelete="set null",
        index=True,
        tracking=True,
    )
    cost_summary = fields.Char(string="Cost Summary", tracking=True)
    total_cost_thb = fields.Float(string="Total Cost (THB)", digits=(16, 2), tracking=True)
    cost_as_of_date = fields.Date(
        string="Cost As Of",
        default=fields.Date.context_today,
        readonly=True,
        help="วันที่ใช้คำนวณต้นทุนรวม (อัปเดตอัตโนมัติทุกวัน)",
        tracking=True,
    )

    def _get_recalculate_cost_values(self, as_of_date=None):
        self.ensure_one()
        if not self.product_convert_id:
            return {}

        as_of_date = (
            self.env["five.five.product.cost"]._normalize_date(as_of_date)
            or self.env["five.five.product.cost"]._normalize_date(self.cost_as_of_date)
            or fields.Date.context_today(self)
        )
        convert = self.env["five.five.product.convert"].browse(self.product_convert_id.id)
        convert.invalidate_recordset(["product_cost_ids"])
        costs = self.env["five.five.product.cost"].search(
            [("product_convert_id", "=", convert.id)]
        )
        costs.invalidate_recordset(["start_calculate_cost", "cost", "type"])

        ProductCost = self.env["five.five.product.cost"]
        totals = ProductCost.compute_convert_cost_totals(convert, as_of_date=as_of_date)
        return {
            "cost_summary": ProductCost.format_cost_amount_summary(totals),
            "total_cost_thb": sum(totals.values()),
            "cost_as_of_date": as_of_date,
        }

    def action_recalculate_cost(self):
        for record in self:
            vals = record._get_recalculate_cost_values(
                as_of_date=fields.Date.context_today(self)
            )
            if vals:
                record.write(vals)
        return True

    def action_open_edit_costs(self):
        self.ensure_one()
        if not self.product_convert_id:
            raise UserError(_("No converted product linked to this inventory line."))
        return self.product_convert_id.action_open_form()

    def action_open_purchase_order(self):
        self.ensure_one()
        if not self.purchase_order_id:
            raise UserError(_("No purchase order linked to this inventory line."))
        return {
            "type": "ir.actions.act_window",
            "name": "Purchase Order",
            "res_model": "five.five.purchase.order",
            "view_mode": "form",
            "res_id": self.purchase_order_id.id,
            "target": "current",
        }

    def action_open_transfer_wizard(self):
        inventories = self.filtered(lambda inv: inv.quantity > 0)
        if not inventories:
            raise UserError(_("No available quantity to transfer."))
        return {
            "type": "ir.actions.act_window",
            "name": "Transfer to Store",
            "res_model": "five.five.warehouse.transfer.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_warehouse_id": inventories[0].warehouse_id.id,
                "default_product_variant_id": inventories[0].product_variant_id.id,
                "default_inventory_ids": inventories.ids,
            },
        }

    @api.model
    def _cron_recalculate_daily_costs(self):
        today = fields.Date.context_today(self)
        inventories = self.search([("product_convert_id", "!=", False)])
        for inventory in inventories:
            vals = inventory._get_recalculate_cost_values(as_of_date=today)
            if vals:
                inventory.with_context(mail_notrack=True).write(vals)
