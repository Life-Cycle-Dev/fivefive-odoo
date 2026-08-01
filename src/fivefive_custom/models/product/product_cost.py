from datetime import date, datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang

COST_TYPE_ORDER = ["fixed", "daily", "weekly", "monthly", "yearly"]
COST_TYPE_LABELS = {
    "fixed": "Fixed",
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
    "yearly": "Yearly",
}


class ProductCost(models.Model):
    _name = "five.five.product.cost"
    _description = "Product Cost"

    product_convert_id = fields.Many2one(
        "five.five.product.convert",
        string="Product Convert",
        required=True,
        ondelete="cascade",
    )

    cost_name = fields.Char(
        string="Cost Name",
        required=True,
    )

    cost = fields.Float(
        string="Cost/Qty (THB)",
        required=True,
        digits=(16, 2),
    )

    type = fields.Selection(
        selection=[
            ('fixed', 'Fixed'),
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('yearly', 'Yearly'),
        ],
        string="Cost Type",
        required=True,
    )

    start_calculate_cost = fields.Date(
        string="Start Calculate Cost",
        default=fields.Date.context_today,
        help="ใช้สำหรับ cost แบบ interval (daily/weekly/monthly/yearly) ว่าจะเริ่มคิดตั้งแต่วันไหน",
    )

    is_auto_from_ci = fields.Boolean(
        string="Auto from CI",
        default=False,
        help="ต้นทุนที่ระบบสร้างอัตโนมัติจาก Commercial Invoice",
    )

    @api.model
    def format_cost_type_summary(self, totals):
        parts = []
        for key in COST_TYPE_ORDER:
            amount = totals.get(key) or 0.0
            if amount:
                formatted = formatLang(self.env, amount, digits=2)
                parts.append(f"{COST_TYPE_LABELS[key]}: {formatted} THB/qty")
        return " · ".join(parts) if parts else _("No costs")

    @api.model
    def _normalize_date(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return fields.Date.from_string(value)
        return value

    @api.model
    def _interval_period_count(self, start_date, as_of_date, cost_type):
        if cost_type == "fixed":
            return 1

        start_date = self._normalize_date(start_date)
        as_of_date = self._normalize_date(as_of_date)
        if not start_date or not as_of_date or as_of_date < start_date:
            return 0

        delta_days = (as_of_date - start_date).days + 1
        if cost_type == "daily":
            return delta_days
        if cost_type == "weekly":
            return (delta_days + 6) // 7
        if cost_type == "monthly":
            return (
                (as_of_date.year - start_date.year) * 12
                + (as_of_date.month - start_date.month)
                + 1
            )
        if cost_type == "yearly":
            return (as_of_date.year - start_date.year) + 1
        return 0

    @api.model
    def compute_convert_cost_totals(self, product_convert, as_of_date=None):
        as_of_date = self._normalize_date(as_of_date) or fields.Date.context_today(self)
        totals = {key: 0.0 for key in COST_TYPE_ORDER}
        quantity = product_convert.quantity or 0.0

        for cost in product_convert.product_cost_ids:
            if cost.type not in totals:
                continue
            periods = self._interval_period_count(
                cost.start_calculate_cost,
                as_of_date,
                cost.type,
            )
            totals[cost.type] += (cost.cost or 0.0) * quantity * periods

        return totals

    @api.model
    def compute_convert_total_cost(self, product_convert, as_of_date=None):
        totals = self.compute_convert_cost_totals(product_convert, as_of_date=as_of_date)
        return sum(totals.values())

    @api.model
    def format_cost_amount_summary(self, totals):
        parts = []
        for key in COST_TYPE_ORDER:
            amount = totals.get(key) or 0.0
            if amount:
                formatted = formatLang(self.env, amount, digits=2)
                parts.append(f"{COST_TYPE_LABELS[key]}: {formatted} THB")
        return " · ".join(parts) if parts else _("No costs")

    @api.model
    def format_frozen_store_cost_summary(self, total_amount):
        if not total_amount:
            return _("No costs")
        formatted = formatLang(self.env, total_amount, digits=2)
        return _("Fixed: %(amount)s THB") % {"amount": formatted}

    def _ff_check_po_not_closed_for_cost_mutation(self, product_convert_ids=None):
        if self.env.context.get("skip_po_closed_convert_check"):
            return
        converts = self.env["five.five.product.convert"]
        if product_convert_ids is not None:
            converts = converts.browse(product_convert_ids)
        else:
            converts = self.mapped("product_convert_id")
        for convert in converts:
            po = convert.purchase_order_id
            if po and po.state == "closed":
                raise UserError(
                    _("Cannot modify costs after the purchase order is closed.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        convert_ids = [
            vals["product_convert_id"]
            for vals in vals_list
            if vals.get("product_convert_id")
        ]
        self._ff_check_po_not_closed_for_cost_mutation(convert_ids)
        records = super().create(vals_list)
        records._sync_linked_inventory_costs()
        return records

    def write(self, vals):
        self._ff_check_po_not_closed_for_cost_mutation()
        res = super().write(vals)
        if any(key in vals for key in ("cost", "type", "start_calculate_cost", "product_convert_id")):
            self._sync_linked_inventory_costs()
        return res

    def unlink(self):
        self._ff_check_po_not_closed_for_cost_mutation()
        converts = self.mapped("product_convert_id")
        res = super().unlink()
        if converts:
            self._sync_inventory_costs_for_converts(converts)
        return res

    def _sync_linked_inventory_costs(self):
        self._sync_inventory_costs_for_converts(self.mapped("product_convert_id"))

    def _sync_inventory_costs_for_converts(self, converts):
        inventories = self.env["five.five.inventory"].search(
            [("product_convert_id", "in", converts.ids)]
        )
        for inventory in inventories:
            vals = inventory._get_recalculate_cost_values(
                as_of_date=fields.Date.context_today(self)
            )
            if vals:
                inventory.write(vals)
