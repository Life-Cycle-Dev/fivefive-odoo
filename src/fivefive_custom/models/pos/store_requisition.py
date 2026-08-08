from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class StoreRequisition(models.Model):
    _name = "five.five.store.requisition"
    _description = "Store Stock Requisition"
    _order = "requested_at desc, id desc"

    number = fields.Char(string="Number", required=True, copy=False, index=True)
    store_id = fields.Many2one("five.five.store", required=True, index=True)
    warehouse_id = fields.Many2one("five.five.warehouse", string="Source Warehouse", index=True)
    warehouse_ids = fields.Many2many(
        "five.five.warehouse",
        "ff_store_req_wh_rel",
        "requisition_id",
        "warehouse_id",
        string="Source Warehouses",
    )
    pos_user_id = fields.Many2one("five.five.store.pos.user", required=True, index=True)
    session_id = fields.Many2one("five.five.store.pos.session", string="POS Session")
    state = fields.Selection(
        [
            ("submitted", "Submitted"),
            ("prepared", "Prepared"),
            ("received", "Received"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        default="submitted",
        required=True,
        index=True,
    )
    note = fields.Text(string="Note")
    requested_at = fields.Datetime(default=fields.Datetime.now, required=True)
    prepared_at = fields.Datetime(string="Prepared At")
    received_at = fields.Datetime(string="Received At")
    done_at = fields.Datetime(string="Done At")
    line_ids = fields.One2many("five.five.store.requisition.line", "requisition_id", string="Lines")
    movement_ids = fields.One2many("five.five.inventory.movement", "requisition_id", string="Movements")
    movement_count = fields.Integer(compute="_compute_movement_count")

    _sql_constraints = [
        (
            "five_five_store_requisition_number_uniq",
            "unique(number)",
            "Requisition number must be unique.",
        ),
    ]

    @api.depends("movement_ids")
    def _compute_movement_count(self):
        for record in self:
            record.movement_count = len(record.movement_ids)

    @api.model
    def _generate_number(self):
        today = fields.Date.context_today(self)
        prefix = f"REQ{today.strftime('%Y%m%d')}"
        last = self.search([("number", "=like", f"{prefix}%")], order="number desc", limit=1)
        if last and last.number and len(last.number) >= len(prefix) + 6:
            try:
                sequence = int(last.number[len(prefix) :]) + 1
            except ValueError:
                sequence = 1
        else:
            sequence = 1
        return f"{prefix}{sequence:06d}"

    @api.model
    def create_from_pos(self, pos_user, lines, note=False, session=False):
        if not lines:
            raise UserError(_("Please add at least one product."))
        requisition_lines = []
        ProductVariant = self.env["five.five.product.variant"]
        for line in lines:
            variant = ProductVariant.browse(int(line.get("product_variant_id"))).exists()
            qty = float(line.get("quantity") or 0)
            if not variant or float_compare(qty, 0, precision_digits=6) <= 0:
                raise UserError(_("Invalid product or quantity."))
            requisition_lines.append(
                (0, 0, {"product_variant_id": variant.id, "requested_qty": qty})
            )
        return self.create(
            {
                "number": self._generate_number(),
                "store_id": pos_user.store_id.id,
                "pos_user_id": pos_user.id,
                "session_id": session.id if session else False,
                "note": note or False,
                "line_ids": requisition_lines,
            }
        )

    def action_open_allocate_wizard(self):
        self.ensure_one()
        if self.state != "submitted":
            raise UserError(_("Only submitted requisitions can be allocated."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Allocate Stock"),
            "res_model": "five.five.store.requisition.allocate.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_requisition_id": self.id,
                "default_store_id": self.store_id.id,
            },
        }

    def action_open_complete_wizard(self):
        self.ensure_one()
        if self.state != "received":
            raise UserError(_("Only received requisitions can be completed and deducted."))
        if not self.movement_ids:
            raise UserError(_("No inventory movements found for this requisition."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Complete & Deduct Stock"),
            "res_model": "five.five.store.requisition.complete.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_requisition_id": self.id,
            },
        }

    def action_open_receive_wizard(self):
        self.ensure_one()
        if self.state != "prepared":
            raise UserError(_("Only prepared requisitions can be marked as received."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Confirm Received Quantities"),
            "res_model": "five.five.store.requisition.receive.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_requisition_id": self.id,
            },
        }

    def _action_complete_with_deduct(self, line_vals):
        self.ensure_one()
        if self.state != "received":
            raise UserError(_("Only received requisitions can be completed and deducted."))
        if not self.movement_ids:
            raise UserError(_("No inventory movements found for this requisition."))

        line_map = {item["line_id"]: item for item in line_vals}
        for req_line in self.line_ids:
            vals = line_map.get(req_line.id)
            if not vals:
                raise UserError(_("Missing deduct quantity for %s.") % req_line.product_variant_id.display_name)
            deduct_qty = int(round(float(vals.get("deduct_qty") or 0.0)))
            if deduct_qty < 0:
                raise UserError(_("Deduct quantity cannot be negative."))

            req_line.write({"deducted_qty": deduct_qty})
            req_line._apply_deduct_qty_to_movements(deduct_qty)

        for movement in self.movement_ids.filtered(lambda m: m.state == "prepared"):
            movement.action_done()
        self.write(
            {
                "state": "done",
                "done_at": fields.Datetime.now(),
            }
        )
        return True

    def action_mark_done(self):
        self.ensure_one()
        return self.action_open_complete_wizard()

    def action_cancel(self):
        for requisition in self:
            if requisition.state == "done":
                raise UserError(_("Completed requisitions cannot be cancelled."))
            requisition.movement_ids.filtered(lambda m: m.state == "prepared").write({"state": "cancelled"})
            requisition.state = "cancelled"
        return True

    def action_mark_received(self, line_vals=None):
        for requisition in self:
            if requisition.state != "prepared":
                raise UserError(_("Only prepared requisitions can be marked as received."))
            if not line_vals:
                raise UserError(_("Please enter received quantity for each item."))

            line_map = {int(item["line_id"]): item for item in line_vals}
            if set(line_map.keys()) != set(requisition.line_ids.ids):
                raise UserError(_("Received quantities must be provided for every line item."))

            has_positive_qty = False
            for req_line in requisition.line_ids:
                received_qty = int(round(float(line_map[req_line.id].get("received_qty") or 0.0)))
                reason = (line_map[req_line.id].get("qty_variance_reason") or "").strip()
                if received_qty < 0:
                    raise UserError(_("Received quantity cannot be negative."))
                if received_qty > 0:
                    has_positive_qty = True
                if received_qty != int(round(req_line.allocated_qty)) and not reason:
                    raise UserError(
                        _(
                            "Please provide a reason for %(product)s because received qty "
                            "(%(received)s) differs from allocated qty (%(allocated)s)."
                        )
                        % {
                            "product": req_line.product_variant_id.display_name,
                            "received": received_qty,
                            "allocated": req_line.allocated_qty,
                        }
                    )
                req_line.write(
                    {
                        "received_qty": received_qty,
                        "qty_variance_reason": reason or False,
                    }
                )

            if not has_positive_qty:
                raise UserError(_("Please enter received quantity for at least one item."))

            requisition.write(
                {
                    "state": "received",
                    "received_at": fields.Datetime.now(),
                }
            )
        return True


class StoreRequisitionLine(models.Model):
    _name = "five.five.store.requisition.line"
    _description = "Store Stock Requisition Line"

    requisition_id = fields.Many2one(
        "five.five.store.requisition",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_variant_id = fields.Many2one("five.five.product.variant", required=True)
    requested_qty = fields.Float(string="Requested Qty", digits=(16, 2), required=True)
    received_qty = fields.Float(string="Received Qty", digits=(16, 2), default=0.0)
    deducted_qty = fields.Float(string="Deducted Qty", digits=(16, 2), default=0.0)
    qty_variance_reason = fields.Char(string="Qty Variance Reason")
    allocated_qty = fields.Float(
        string="Allocated Qty",
        compute="_compute_allocated_qty",
        store=True,
        digits=(16, 2),
    )

    @api.depends(
        "requisition_id.movement_ids.quantity",
        "requisition_id.movement_ids.state",
        "requisition_id.movement_ids.requisition_line_id",
    )
    def _compute_allocated_qty(self):
        for line in self:
            movements = line.requisition_id.movement_ids.filtered(
                lambda movement: movement.requisition_line_id.id == line.id
                and movement.state != "cancelled"
            )
            line.allocated_qty = sum(movements.mapped("quantity"))

    def _apply_deduct_qty_to_movements(self, deduct_qty):
        self.ensure_one()
        movements = self.requisition_id.movement_ids.filtered(
            lambda movement: movement.requisition_line_id.id == self.id
            and movement.state == "prepared"
        )
        if float_is_zero(deduct_qty, precision_digits=2):
            movements.write({"state": "cancelled"})
            return

        total_allocated = sum(movements.mapped("quantity"))
        if float_is_zero(total_allocated, precision_digits=2):
            raise UserError(
                _("No prepared allocation found for %s.")
                % self.product_variant_id.display_name
            )

        ratio = deduct_qty / total_allocated
        for movement in movements:
            inventory = movement.warehouse_inventory_id
            new_qty = movement.quantity * ratio
            if float_compare(new_qty, 0, precision_digits=6) <= 0:
                movement.write({"state": "cancelled"})
                continue
            transfer_cost = movement.transfer_cost_thb * ratio
            if not transfer_cost and inventory.quantity > 0:
                transfer_cost = (inventory.total_cost_thb / inventory.quantity) * new_qty
            movement.write(
                {
                    "quantity": new_qty,
                    "transfer_cost_thb": transfer_cost,
                }
            )
