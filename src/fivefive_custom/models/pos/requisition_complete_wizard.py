from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StoreRequisitionCompleteWizard(models.TransientModel):
    _name = "five.five.store.requisition.complete.wizard"
    _description = "Complete store requisition and deduct stock"

    requisition_id = fields.Many2one("five.five.store.requisition", required=True, readonly=True)
    line_ids = fields.One2many(
        "five.five.store.requisition.complete.wizard.line",
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
            (
                0,
                0,
                {
                    "requisition_line_id": line.id,
                    "deduct_qty": line.received_qty,
                },
            )
            for line in requisition.line_ids
        ]
        return res

    def action_confirm(self):
        self.ensure_one()
        for wizard_line in self.line_ids:
            if not wizard_line.requisition_line_id:
                raise UserError(_("Missing requisition line reference. Please close and reopen the wizard."))
            deduct_qty = int(round(wizard_line.deduct_qty))
            if deduct_qty < 0:
                raise UserError(_("Deduct quantity cannot be negative for %s.") % wizard_line.product_variant_id.display_name)

        line_vals = [
            {
                "line_id": wizard_line.requisition_line_id.id,
                "deduct_qty": int(round(wizard_line.deduct_qty)),
            }
            for wizard_line in self.line_ids
        ]
        self.requisition_id._action_complete_with_deduct(line_vals)
        return {"type": "ir.actions.act_window_close"}


class StoreRequisitionCompleteWizardLine(models.TransientModel):
    _name = "five.five.store.requisition.complete.wizard.line"
    _description = "Store requisition complete wizard line"

    wizard_id = fields.Many2one(
        "five.five.store.requisition.complete.wizard",
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
    received_qty = fields.Float(related="requisition_line_id.received_qty", readonly=True)
    allocated_qty = fields.Float(related="requisition_line_id.allocated_qty", readonly=True)
    deduct_qty = fields.Float(string="Deduct Qty", digits=(16, 2))
    qty_variance_reason = fields.Char(
        related="requisition_line_id.qty_variance_reason",
        string="Store Reason",
        readonly=True,
    )
