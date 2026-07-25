from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class StorePosOrderLineDeduction(models.Model):
    _name = "five.five.store.pos.order.line.deduction"
    _description = "POS Order Line Stock Deduction"

    line_id = fields.Many2one(
        "five.five.store.pos.order.line",
        required=True,
        ondelete="cascade",
        index=True,
    )
    lot_number = fields.Char(string="Lot Number", required=True)
    quantity = fields.Float(string="Quantity", digits=(16, 6), required=True)
    cost_thb = fields.Float(string="Cost (THB)", digits=(16, 2), required=True)
    quality_note = fields.Char(string="Quality Note")
    purchase_order_id = fields.Many2one("five.five.purchase.order", ondelete="set null")
    source_inventory_id = fields.Many2one("five.five.inventory", ondelete="set null")


class StorePosOrder(models.Model):
    _name = "five.five.store.pos.order"
    _description = "Store POS Order"
    _order = "order_date desc, id desc"

    number = fields.Char(string="Order Number", required=True, copy=False, index=True)
    session_id = fields.Many2one(
        "five.five.store.pos.session",
        string="Session",
        required=True,
        ondelete="restrict",
        index=True,
    )
    store_id = fields.Many2one("five.five.store", required=True, index=True)
    pos_user_id = fields.Many2one("five.five.store.pos.user", required=True, index=True)
    order_date = fields.Datetime(string="Order Date", default=fields.Datetime.now, required=True)
    state = fields.Selection(
        [("done", "Done"), ("cancelled", "Cancelled")],
        default="done",
        required=True,
    )
    line_ids = fields.One2many("five.five.store.pos.order.line", "order_id", string="Lines")
    subtotal = fields.Float(string="Subtotal (THB)", digits=(16, 2))
    discount_type = fields.Selection(
        [("percent", "Percent"), ("fixed", "Fixed Amount")],
        string="Discount Type",
    )
    discount_value = fields.Float(string="Discount Value", digits=(16, 2))
    discount_amount = fields.Float(string="Discount Amount (THB)", digits=(16, 2))
    total = fields.Float(string="Total (THB)", digits=(16, 2))
    amount_paid = fields.Float(string="Amount Paid (THB)", digits=(16, 2))
    change_amount = fields.Float(string="Change (THB)", digits=(16, 2))
    return_stock = fields.Boolean(string="Returned Stock on Cancel", copy=False)
    cancel_reason = fields.Text(string="Cancel Reason", copy=False)
    cancelled_at = fields.Datetime(string="Cancelled At", copy=False)

    _sql_constraints = [
        (
            "five_five_store_pos_order_number_uniq",
            "unique(number)",
            "Order number must be unique.",
        ),
    ]

    @api.model
    def _generate_order_number(self):
        today = fields.Date.context_today(self)
        prefix = today.strftime("%Y%m%d")
        last_order = self.search([("number", "=like", f"{prefix}%")], order="number desc", limit=1)
        if last_order and last_order.number and len(last_order.number) >= 14:
            try:
                sequence = int(last_order.number[8:]) + 1
            except ValueError:
                sequence = 1
        else:
            sequence = 1
        return f"{prefix}{sequence:06d}"

    @api.model
    def _compute_discount_amount(self, subtotal, discount_type, discount_value):
        discount_value = discount_value or 0.0
        if not discount_type or float_compare(discount_value, 0, precision_digits=2) <= 0:
            return 0.0
        if discount_type == "percent":
            if discount_value > 100:
                raise UserError(_("Discount percent cannot exceed 100."))
            return subtotal * (discount_value / 100.0)
        return min(discount_value, subtotal)

    @api.model
    def create_order(self, session, pos_user, lines, discount_type=False, discount_value=0.0, amount_paid=0.0):
        if session.state != "open":
            raise UserError(_("Session is not open."))
        if session.pos_user_id.id != pos_user.id:
            raise UserError(_("Session does not belong to this user."))
        if not lines:
            raise UserError(_("Please add at least one product."))

        order_lines = []
        subtotal = 0.0
        StoreInventory = self.env["five.five.store.inventory"]
        ProductVariant = self.env["five.five.product.variant"]

        for line in lines:
            variant_id = line.get("product_variant_id")
            qty = float(line.get("quantity") or 0)
            if not variant_id or float_compare(qty, 0, precision_digits=6) <= 0:
                raise UserError(_("Invalid product or quantity."))
            variant = ProductVariant.browse(int(variant_id)).exists()
            if not variant:
                raise UserError(_("Product not found."))
            if float_compare(variant.sell_price_thb, 0, precision_digits=2) <= 0:
                raise UserError(_("Sell price is not set for %(product)s.") % {"product": variant.display_name})

            available_qty = sum(
                StoreInventory.search(
                    [
                        ("store_id", "=", session.store_id.id),
                        ("product_variant_id", "=", variant.id),
                        ("quantity", ">", 0),
                    ]
                ).mapped("quantity")
            )
            if float_compare(qty, available_qty, precision_digits=6) > 0:
                raise UserError(
                    _("Insufficient stock for %(product)s. Available: %(qty)s")
                    % {"product": variant.display_name, "qty": available_qty}
                )

            line_subtotal = variant.sell_price_thb * qty
            subtotal += line_subtotal
            order_lines.append(
                {
                    "product_variant_id": variant.id,
                    "quantity": qty,
                    "unit_price": variant.sell_price_thb,
                    "subtotal": line_subtotal,
                }
            )

        discount_amount = self._compute_discount_amount(subtotal, discount_type, discount_value)
        total = subtotal - discount_amount
        if float_compare(total, 0, precision_digits=2) < 0:
            raise UserError(_("Total amount is invalid."))
        if float_compare(amount_paid, total, precision_digits=2) < 0:
            raise UserError(_("Amount paid is less than total."))

        change_amount = amount_paid - total
        order = self.create(
            {
                "number": self._generate_order_number(),
                "session_id": session.id,
                "store_id": session.store_id.id,
                "pos_user_id": pos_user.id,
                "subtotal": subtotal,
                "discount_type": discount_type or False,
                "discount_value": discount_value or 0.0,
                "discount_amount": discount_amount,
                "total": total,
                "amount_paid": amount_paid,
                "change_amount": change_amount,
                "line_ids": [(0, 0, line_vals) for line_vals in order_lines],
            }
        )
        order._deduct_store_inventory()
        return order

    def action_cancel_from_pos(self, return_stock=False, cancel_reason=False):
        self.ensure_one()
        if self.state != "done":
            raise UserError(_("Only completed orders can be cancelled."))
        reason = (cancel_reason or "").strip()
        if not return_stock and not reason:
            raise UserError(_("Please provide a reason when not returning stock to store inventory."))
        if return_stock:
            self._return_store_inventory()
        self.write(
            {
                "state": "cancelled",
                "return_stock": return_stock,
                "cancel_reason": reason or False,
                "cancelled_at": fields.Datetime.now(),
            }
        )
        return True

    def _deduct_store_inventory(self):
        StoreInventory = self.env["five.five.store.inventory"]
        for order in self:
            for line in order.line_ids:
                remaining = line.quantity
                lots = StoreInventory.search(
                    [
                        ("store_id", "=", order.store_id.id),
                        ("product_variant_id", "=", line.product_variant_id.id),
                        ("quantity", ">", 0),
                    ],
                    order="id",
                )
                deduction_vals = []
                for lot in lots:
                    if float_is_zero(remaining, precision_digits=6):
                        break
                    old_qty = lot.quantity
                    take_qty = min(old_qty, remaining)
                    cost_taken = lot.total_cost_thb * (take_qty / old_qty) if old_qty else 0.0
                    deduction_vals.append(
                        (
                            0,
                            0,
                            {
                                "lot_number": lot.lot_number,
                                "quantity": take_qty,
                                "cost_thb": cost_taken,
                                "quality_note": lot.quality_note,
                                "purchase_order_id": lot.purchase_order_id.id,
                                "source_inventory_id": lot.source_inventory_id.id,
                            },
                        )
                    )
                    if float_compare(old_qty, 0, precision_digits=6) > 0:
                        lot.total_cost_thb = lot.total_cost_thb * ((old_qty - take_qty) / old_qty)
                    lot.quantity = old_qty - take_qty
                    remaining -= take_qty
                    if float_is_zero(lot.quantity, precision_digits=6):
                        lot.unlink()
                if deduction_vals:
                    line.write({"deduction_ids": deduction_vals})
                if not float_is_zero(remaining, precision_digits=6):
                    raise UserError(
                        _("Unable to deduct stock for %(product)s.")
                        % {"product": line.product_variant_id.display_name}
                    )

    def _return_store_inventory(self):
        StoreInventory = self.env["five.five.store.inventory"]
        ProductCost = self.env["five.five.product.cost"]
        for order in self:
            for line in order.line_ids:
                if line.deduction_ids:
                    for deduction in line.deduction_ids:
                        self._return_deduction(order, line, deduction, StoreInventory, ProductCost)
                else:
                    self._return_line_legacy(order, line, StoreInventory, ProductCost)

    def _return_deduction(self, order, line, deduction, StoreInventory, ProductCost):
        existing = StoreInventory.search(
            [
                ("store_id", "=", order.store_id.id),
                ("lot_number", "=", deduction.lot_number),
            ],
            limit=1,
        )
        if existing:
            new_qty = existing.quantity + deduction.quantity
            new_cost = existing.total_cost_thb + deduction.cost_thb
            existing.write(
                {
                    "quantity": new_qty,
                    "total_cost_thb": new_cost,
                    "cost_summary": ProductCost.format_frozen_store_cost_summary(new_cost),
                }
            )
            return
        StoreInventory.create(
            {
                "store_id": order.store_id.id,
                "product_variant_id": line.product_variant_id.id,
                "lot_number": deduction.lot_number,
                "quantity": deduction.quantity,
                "quality_note": deduction.quality_note,
                "purchase_order_id": deduction.purchase_order_id.id,
                "source_inventory_id": deduction.source_inventory_id.id,
                "total_cost_thb": deduction.cost_thb,
                "cost_summary": ProductCost.format_frozen_store_cost_summary(deduction.cost_thb),
                "cost_as_of_date": fields.Date.context_today(self),
            }
        )

    def _return_line_legacy(self, order, line, StoreInventory, ProductCost):
        lot_number = f"RETURN-{order.number}-{line.id}"
        existing = StoreInventory.search(
            [
                ("store_id", "=", order.store_id.id),
                ("lot_number", "=", lot_number),
            ],
            limit=1,
        )
        if existing:
            existing.quantity += line.quantity
            return
        StoreInventory.create(
            {
                "store_id": order.store_id.id,
                "product_variant_id": line.product_variant_id.id,
                "lot_number": lot_number,
                "quantity": line.quantity,
                "quality_note": _("Returned from cancelled order %(order)s") % {"order": order.number},
                "total_cost_thb": 0.0,
                "cost_summary": ProductCost.format_frozen_store_cost_summary(0.0),
                "cost_as_of_date": fields.Date.context_today(self),
            }
        )


class StorePosOrderLine(models.Model):
    _name = "five.five.store.pos.order.line"
    _description = "Store POS Order Line"

    order_id = fields.Many2one("five.five.store.pos.order", required=True, ondelete="cascade", index=True)
    product_variant_id = fields.Many2one("five.five.product.variant", required=True)
    quantity = fields.Float(string="Quantity", digits=(16, 2), required=True)
    unit_price = fields.Float(string="Unit Price (THB)", digits=(16, 2), required=True)
    subtotal = fields.Float(string="Subtotal (THB)", digits=(16, 2), required=True)
    deduction_ids = fields.One2many(
        "five.five.store.pos.order.line.deduction",
        "line_id",
        string="Stock Deductions",
        copy=False,
    )
