from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero
from odoo.tools.misc import formatLang


class StoreInventoryAdjustWizard(models.TransientModel):
    _name = "five.five.store.inventory.adjust.wizard"
    _description = "Store inventory adjustment wizard"

    store_id = fields.Many2one(
        "five.five.store",
        string="Store",
        required=True,
    )
    reason = fields.Text(string="Reason", required=True)
    line_ids = fields.One2many(
        "five.five.store.inventory.adjust.wizard.line",
        "wizard_id",
        string="Lines",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        store_id = res.get("store_id") or self.env.context.get("default_store_id")
        if not store_id or "line_ids" not in fields_list or res.get("line_ids"):
            return res

        store = self.env["five.five.store"].browse(store_id)
        res["store_id"] = store.id
        res["line_ids"] = [
            (0, 0, {"store_inventory_id": line.id})
            for line in store.store_inventory_ids
        ]
        return res

    def action_confirm(self):
        self.ensure_one()
        reason = (self.reason or "").strip()
        if not reason:
            raise UserError(_("Please provide a reason for this adjustment."))

        lines = self.line_ids.filtered(lambda line: float_compare(line.quantity, 0, precision_digits=6) > 0)
        if not lines:
            raise UserError(_("Please enter an adjustment quantity for at least one product line."))

        adjustments = self.env["five.five.store.inventory.adjustment"]
        for line in lines:
            adjustments |= line._apply_adjustment(reason)

        self.store_id.message_post(
            body=_(
                "Store inventory adjusted: %(count)s line(s). Reason: %(reason)s"
            )
            % {"count": len(adjustments), "reason": reason}
        )
        return {"type": "ir.actions.act_window_close"}


class StoreInventoryAdjustWizardLine(models.TransientModel):
    _name = "five.five.store.inventory.adjust.wizard.line"
    _description = "Store inventory adjustment wizard line"

    wizard_id = fields.Many2one(
        "five.five.store.inventory.adjust.wizard",
        required=True,
        ondelete="cascade",
    )
    store_inventory_id = fields.Many2one(
        "five.five.store.inventory",
        string="Store Inventory",
        required=True,
        ondelete="cascade",
    )
    product_variant_id = fields.Many2one(
        related="store_inventory_id.product_variant_id",
        readonly=True,
    )
    lot_number = fields.Char(related="store_inventory_id.lot_number", readonly=True)
    quantity_on_hand = fields.Float(
        related="store_inventory_id.quantity",
        string="Qty On Hand",
        readonly=True,
        digits=(16, 6),
    )
    adjustment_type = fields.Selection(
        [
            ("increase", "Increase"),
            ("decrease", "Decrease"),
        ],
        string="Adjust",
        required=True,
        default="increase",
    )
    quantity = fields.Float(string="Adjust Qty", digits=(16, 6), default=0.0)

    def _apply_adjustment(self, reason):
        self.ensure_one()
        inventory = self.store_inventory_id
        if inventory.store_id != self.wizard_id.store_id:
            raise UserError(_("Store inventory line does not belong to this store."))

        adjust_qty = self.quantity or 0.0
        if float_compare(adjust_qty, 0, precision_digits=6) <= 0:
            raise UserError(_("Adjustment quantity must be greater than zero."))

        old_qty = inventory.quantity or 0.0
        old_cost = inventory.total_cost_thb or 0.0
        ProductCost = self.env["five.five.product.cost"]
        Adjustment = self.env["five.five.store.inventory.adjustment"]

        if self.adjustment_type == "decrease":
            if float_compare(adjust_qty, old_qty, precision_digits=6) > 0:
                raise UserError(
                    _("Cannot decrease %(qty)s for %(product)s (Lot %(lot)s). Only %(available)s available.")
                    % {
                        "qty": formatLang(self.env, adjust_qty, digits=2),
                        "product": inventory.product_variant_id.display_name,
                        "lot": inventory.lot_number or "-",
                        "available": formatLang(self.env, old_qty, digits=2),
                    }
                )
            remove_cost = old_cost * (adjust_qty / old_qty) if old_qty else 0.0
            new_qty = old_qty - adjust_qty
            new_cost = old_cost - remove_cost
            qty_change = -adjust_qty
            adjustment_type = "decrease"
        else:
            unit_cost = old_cost / old_qty if old_qty else 0.0
            add_cost = unit_cost * adjust_qty
            new_qty = old_qty + adjust_qty
            new_cost = old_cost + add_cost
            qty_change = adjust_qty
            adjustment_type = "increase"

        adjustment = Adjustment.create(
            {
                "store_id": self.wizard_id.store_id.id,
                "store_inventory_id": inventory.id,
                "product_variant_id": inventory.product_variant_id.id,
                "lot_number": inventory.lot_number,
                "adjustment_type": adjustment_type,
                "quantity_before": old_qty,
                "quantity_change": qty_change,
                "quantity_after": new_qty,
                "cost_before": old_cost,
                "cost_after": new_cost,
                "reason": reason,
            }
        )

        if float_is_zero(new_qty, precision_digits=6):
            inventory.unlink()
        else:
            inventory.write(
                {
                    "quantity": new_qty,
                    "total_cost_thb": new_cost,
                    "cost_summary": ProductCost.format_frozen_store_cost_summary(new_cost),
                }
            )
        return adjustment
