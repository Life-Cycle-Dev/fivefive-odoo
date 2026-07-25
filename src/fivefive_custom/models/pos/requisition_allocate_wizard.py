from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StoreRequisitionAllocateWizard(models.TransientModel):
    _name = "five.five.store.requisition.allocate.wizard"
    _description = "Allocate stock for store requisition"

    requisition_id = fields.Many2one("five.five.store.requisition", required=True)
    store_id = fields.Many2one("five.five.store", required=True)
    warehouse_id = fields.Many2one(
        "five.five.warehouse",
        string="Source Warehouse",
        required=True,
        domain=[("active", "=", True)],
    )
    line_ids = fields.One2many(
        "five.five.store.requisition.allocate.wizard.line",
        "wizard_id",
        string="Allocations",
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
        return res

    @api.onchange("warehouse_id", "requisition_id")
    def _onchange_warehouse_id(self):
        if not self.warehouse_id or not self.requisition_id:
            return
        self._load_lines_for_warehouse()

    def _load_lines_for_warehouse(self):
        self.ensure_one()
        Inventory = self.env["five.five.inventory"]
        commands = [(5, 0, 0)]
        for req_line in self.requisition_id.line_ids:
            inventories = Inventory.search(
                [
                    ("warehouse_id", "=", self.warehouse_id.id),
                    ("product_variant_id", "=", req_line.product_variant_id.id),
                    ("quantity", ">", 0),
                ],
                order="lot_number, id",
            )
            for inventory in inventories:
                commands.append(
                    (
                        0,
                        0,
                        {
                            "requisition_line_id": req_line.id,
                            "warehouse_inventory_id": inventory.id,
                            "quantity": 0.0,
                        },
                    )
                )
        self.line_ids = commands

    def action_confirm(self):
        self.ensure_one()
        if self.requisition_id.state != "submitted":
            raise UserError(_("This requisition is no longer waiting for allocation."))
        if not self.warehouse_id:
            raise UserError(_("Please select a source warehouse."))

        allocation_lines = self.line_ids.filtered(
            lambda line: line.warehouse_inventory_id and line.quantity > 0
        )
        if not allocation_lines:
            raise UserError(_("Please enter allocation quantity for at least one lot."))

        Movement = self.env["five.five.inventory.movement"]
        for req_line in self.requisition_id.line_ids:
            line_allocations = allocation_lines.filtered(
                lambda line: line.requisition_line_id.id == req_line.id
            )
            allocated_qty = sum(line_allocations.mapped("quantity"))
            if float_compare(allocated_qty, req_line.requested_qty, precision_digits=6) > 0:
                raise UserError(
                    _("Allocated quantity exceeds requested quantity for %(product)s.")
                    % {"product": req_line.product_variant_id.display_name}
                )

        for line in allocation_lines:
            inventory = line.warehouse_inventory_id
            if float_compare(line.quantity, inventory.quantity, precision_digits=6) > 0:
                raise UserError(
                    _("Allocation for lot %(lot)s exceeds available quantity.")
                    % {"lot": inventory.lot_number or "-"}
                )
            transfer_cost = 0.0
            if inventory.quantity > 0:
                transfer_cost = (inventory.total_cost_thb / inventory.quantity) * line.quantity
            Movement.create(
                {
                    "requisition_id": self.requisition_id.id,
                    "requisition_line_id": line.requisition_line_id.id,
                    "warehouse_inventory_id": inventory.id,
                    "store_id": self.store_id.id,
                    "quantity": line.quantity,
                    "transfer_cost_thb": transfer_cost,
                    "state": "prepared",
                }
            )

        self.requisition_id.write(
            {
                "state": "prepared",
                "warehouse_id": self.warehouse_id.id,
                "prepared_at": fields.Datetime.now(),
            }
        )
        return {"type": "ir.actions.act_window_close"}


class StoreRequisitionAllocateWizardLine(models.TransientModel):
    _name = "five.five.store.requisition.allocate.wizard.line"
    _description = "Allocate stock wizard line"

    wizard_id = fields.Many2one(
        "five.five.store.requisition.allocate.wizard",
        required=True,
        ondelete="cascade",
    )
    requisition_line_id = fields.Many2one(
        "five.five.store.requisition.line",
        required=True,
    )
    product_variant_id = fields.Many2one(
        related="requisition_line_id.product_variant_id",
        readonly=True,
    )
    requested_qty = fields.Float(related="requisition_line_id.requested_qty", readonly=True)
    warehouse_inventory_id = fields.Many2one("five.five.inventory", string="Warehouse Lot")
    lot_number = fields.Char(related="warehouse_inventory_id.lot_number", readonly=True)
    available_quantity = fields.Float(related="warehouse_inventory_id.quantity", readonly=True)
    quality_note = fields.Char(related="warehouse_inventory_id.quality_note", readonly=True)
    quantity = fields.Float(string="Allocate Qty", default=0.0)
