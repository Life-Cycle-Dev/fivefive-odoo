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
            "target": "new",
            "context": {
                "default_requisition_id": self.id,
                "default_store_id": self.store_id.id,
            },
        }

    def action_mark_done(self):
        for requisition in self:
            if requisition.state not in ("prepared", "received"):
                raise UserError(_("Only prepared or received requisitions can be completed."))
            if not requisition.movement_ids:
                raise UserError(_("No inventory movements found for this requisition."))
            for movement in requisition.movement_ids.filtered(lambda m: m.state == "prepared"):
                movement.action_done()
            requisition.write(
                {
                    "state": "done",
                    "done_at": fields.Datetime.now(),
                }
            )
        return True

    def action_cancel(self):
        for requisition in self:
            if requisition.state == "done":
                raise UserError(_("Completed requisitions cannot be cancelled."))
            requisition.movement_ids.filtered(lambda m: m.state == "prepared").write({"state": "cancelled"})
            requisition.state = "cancelled"
        return True

    def action_mark_received(self):
        for requisition in self:
            if requisition.state != "prepared":
                raise UserError(_("Only prepared requisitions can be marked as received."))
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
