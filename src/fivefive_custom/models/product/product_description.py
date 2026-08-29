from odoo import fields, models


class ProductDescription(models.Model):
    _name = "five.five.product.description"
    _description = "Product Description"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _sql_constraints = [
        ("five_five_product_description_name_uniq", "unique(name)", "Description must be unique."),
    ]

    name = fields.Char(string="Name", required=True, tracking=True)
    active = fields.Boolean(string="Active", default=True, tracking=True)
