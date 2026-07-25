from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StoreRequisitionAllocateWizard(models.TransientModel):
    _name = "five.five.store.requisition.allocate.wizard"
    _description = "Allocate stock for store requisition"

    requisition_id = fields.Many2one("five.five.store.requisition", required=True)
    store_id = fields.Many2one("five.five.store", required=True)
    warehouse_ids = fields.Many2many(
        "five.five.warehouse",
        "ff_req_alloc_wh_rel",
        "wizard_id",
        "warehouse_id",
        string="Source Warehouses",
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
        if requisition.warehouse_ids:
            res["warehouse_ids"] = [(6, 0, requisition.warehouse_ids.ids)]
        elif requisition.warehouse_id:
            res["warehouse_ids"] = [(6, 0, [requisition.warehouse_id.id])]
        return res

    @api.onchange("warehouse_ids", "requisition_id")
    def _onchange_warehouse_ids(self):
        if not self.warehouse_ids or not self.requisition_id:
            self.line_ids = [(5, 0, 0)]
            return
        self._load_lines_for_warehouses()

    def _load_lines_for_warehouses(self):
        self.ensure_one()
        Inventory = self.env["five.five.inventory"]
        commands = [(5, 0, 0)]
        for req_line in self.requisition_id.line_ids:
            inventories = Inventory.search(
                [
                    ("warehouse_id", "in", self.warehouse_ids.ids),
                    ("product_variant_id", "=", req_line.product_variant_id.id),
                    ("quantity", ">", 0),
                ],
                order="warehouse_id, lot_number, id",
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
        if not self.warehouse_ids:
            raise UserError(_("Please select at least one source warehouse."))

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
            if inventory.warehouse_id not in self.warehouse_ids:
                raise UserError(
                    _("Lot %(lot)s does not belong to the selected warehouses.")
                    % {"lot": inventory.lot_number or "-"}
                )
            if float_compare(line.quantity, inventory.quantity, precision_digits=6) > 0:
                raise UserError(
                    _("Allocation for lot %(lot)s exceeds available quantity.")
                    % {"lot": inventory.lot_number or "-"}
                )
            transfer_cost = line.allocation_cost_thb
            if not transfer_cost and inventory.quantity > 0:
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

        warehouse_vals = {"warehouse_ids": [(6, 0, self.warehouse_ids.ids)]}
        if len(self.warehouse_ids) == 1:
            warehouse_vals["warehouse_id"] = self.warehouse_ids.id
        else:
            warehouse_vals["warehouse_id"] = False

        self.requisition_id.write(
            {
                **warehouse_vals,
                "state": "prepared",
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
    warehouse_id = fields.Many2one(
        related="warehouse_inventory_id.warehouse_id",
        readonly=True,
    )
    lot_number = fields.Char(related="warehouse_inventory_id.lot_number", readonly=True)
    available_quantity = fields.Float(related="warehouse_inventory_id.quantity", readonly=True)
    quality_note = fields.Char(related="warehouse_inventory_id.quality_note", readonly=True)
    lot_total_cost_thb = fields.Float(
        related="warehouse_inventory_id.total_cost_thb",
        readonly=True,
    )
    unit_cost_thb = fields.Float(
        string="Unit Cost (THB)",
        compute="_compute_cost_fields",
        digits=(16, 2),
        readonly=True,
    )
    allocation_cost_thb = fields.Float(
        string="Allocation Cost (THB)",
        compute="_compute_cost_fields",
        digits=(16, 2),
        readonly=True,
    )
    quantity = fields.Float(string="Allocate Qty", default=0.0)

    @api.depends(
        "warehouse_inventory_id.total_cost_thb",
        "warehouse_inventory_id.quantity",
        "quantity",
    )
    def _compute_cost_fields(self):
        for line in self:
            inventory = line.warehouse_inventory_id
            if inventory and inventory.quantity > 0:
                line.unit_cost_thb = inventory.total_cost_thb / inventory.quantity
            else:
                line.unit_cost_thb = 0.0
            line.allocation_cost_thb = line.unit_cost_thb * line.quantity
