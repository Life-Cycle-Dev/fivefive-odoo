from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class StoreRequisitionReceiveWizard(models.TransientModel):
    _name = "five.five.store.requisition.receive.wizard"
    _description = "Confirm received quantities for store requisition"

    requisition_id = fields.Many2one("five.five.store.requisition", required=True, readonly=True)
    line_ids = fields.One2many(
        "five.five.store.requisition.receive.wizard.line",
        "wizard_id",
        string="Lines",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        requisition_id = res.get("requisition_id") or self.env.context.get("default_requisition_id")
        if not requisition_id:
            return res
        requisition = self.env["five.five.store.requisition"].browse(requisition_id).exists()
        if not requisition:
            return res
        res["requisition_id"] = requisition.id
        res["line_ids"] = [
            (0, 0, {"requisition_line_id": line.id, "received_qty": line.allocated_qty})
            for line in requisition.line_ids
        ]
        return res

    def action_confirm(self):
        self.ensure_one()
        line_vals = []
        for wizard_line in self.line_ids:
            reason = (wizard_line.qty_variance_reason or "").strip()
            if float_compare(wizard_line.received_qty, wizard_line.allocated_qty, precision_digits=2) != 0:
                if not reason:
                    raise UserError(
                        _(
                            "Please provide a reason for %(product)s because received qty "
                            "(%(received)s) differs from allocated qty (%(allocated)s)."
                        )
                        % {
                            "product": wizard_line.product_variant_id.display_name,
                            "received": wizard_line.received_qty,
                            "allocated": wizard_line.allocated_qty,
                        }
                    )
            line_vals.append(
                {
                    "line_id": wizard_line.requisition_line_id.id,
                    "received_qty": wizard_line.received_qty,
                    "qty_variance_reason": reason or False,
                }
            )
        self.requisition_id.action_mark_received(line_vals)
        return {"type": "ir.actions.act_window_close"}


class StoreRequisitionReceiveWizardLine(models.TransientModel):
    _name = "five.five.store.requisition.receive.wizard.line"
    _description = "Store requisition receive wizard line"

    wizard_id = fields.Many2one(
        "five.five.store.requisition.receive.wizard",
        required=True,
        ondelete="cascade",
    )
    requisition_line_id = fields.Many2one(
        "five.five.store.requisition.line",
        required=True,
        readonly=True,
    )
    product_variant_id = fields.Many2one(
        related="requisition_line_id.product_variant_id",
        readonly=True,
    )
    requested_qty = fields.Float(related="requisition_line_id.requested_qty", readonly=True)
    allocated_qty = fields.Float(related="requisition_line_id.allocated_qty", readonly=True)
    received_qty = fields.Float(string="Received Qty", digits=(16, 2))
    qty_variance_reason = fields.Char(string="Reason (if qty differs)")
