from odoo import models, fields


class Warehouse(models.Model):
    _name = "five.five.warehouse"
    _description = "Warehouse"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _sql_constraints = [
        ("five_five_warehouse_code_uniq", "unique(code)", "Warehouse code must be unique."),
    ]

    name = fields.Char(string="Name", required=True, tracking=True)
    code = fields.Char(string="Code", required=True, tracking=True)
    address = fields.Char(string="Name", tracking=True)
    phone = fields.Char(string="Phone", tracking=True)
    image = fields.Image(string="Image", max_width=1920, max_height=1920, tracking=True)
    inventory_ids = fields.One2many(
        "five.five.inventory",
        "warehouse_id",
        string="Warehouse",
        context={"active_test": False},
        tracking=True,
    )

    active = fields.Boolean(string="Active", default=True, tracking=True)
