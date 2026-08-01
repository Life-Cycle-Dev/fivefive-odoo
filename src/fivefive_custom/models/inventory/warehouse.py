from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Warehouse(models.Model):
    _name = "five.five.warehouse"
    _description = "Warehouse"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _sql_constraints = [
        ("five_five_warehouse_code_uniq", "unique(code)", "Warehouse code must be unique."),
    ]

    image = fields.Image(string="Image", max_width=1920, max_height=1920)
    name = fields.Char(string="Name", required=True, tracking=True)
    code = fields.Char(string="Code", required=True, tracking=True)
    address = fields.Char(string="Address", tracking=True)
    phone = fields.Char(string="Phone", tracking=True)
    inventory_ids = fields.One2many(
        "five.five.inventory",
        "warehouse_id",
        string="Warehouse",
        context={"active_test": False},
        tracking=True,
    )

    active = fields.Boolean(string="Active", default=True, tracking=True)
    inventory_total_cost_thb = fields.Float(
        string="Total Inventory Cost (THB)",
        compute="_compute_inventory_total_cost_thb",
        digits=(16, 2),
    )

    @api.depends("inventory_ids.total_cost_thb")
    def _compute_inventory_total_cost_thb(self):
        for warehouse in self:
            warehouse.inventory_total_cost_thb = sum(warehouse.inventory_ids.mapped("total_cost_thb"))

    def action_open_transfer_wizard(self):
        self.ensure_one()
        if not self.inventory_ids.filtered(lambda inv: inv.quantity > 0):
            raise UserError(_("No inventory available to transfer."))
        return {
            "type": "ir.actions.act_window",
            "name": "Transfer to Store",
            "res_model": "five.five.warehouse.transfer.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_warehouse_id": self.id,
            },
        }

    def action_open_inventory_receipt_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Add Inventory"),
            "res_model": "five.five.warehouse.inventory.receipt.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_warehouse_id": self.id,
            },
        }
