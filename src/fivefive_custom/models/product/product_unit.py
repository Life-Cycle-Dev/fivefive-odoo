from odoo import models, fields


class ProductUnit(models.Model):
    _name = "five.five.product.unit"
    _description = "Product Unit"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _sql_constraints = [
        ("five_five_product_unit_name_uniq", "unique(name)", "Unit name must be unique."),
    ]

    name = fields.Char(string="Name", required=True, tracking=True)
    active = fields.Boolean(string="Active", default=True, tracking=True)
