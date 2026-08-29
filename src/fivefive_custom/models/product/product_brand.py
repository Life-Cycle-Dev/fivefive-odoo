from odoo import fields, models


class ProductBrand(models.Model):
    _name = "five.five.product.brand"
    _description = "Product Brand"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _sql_constraints = [
        ("five_five_product_brand_name_uniq", "unique(name)", "Brand name must be unique."),
    ]

    name = fields.Char(string="Name", required=True, tracking=True)
    active = fields.Boolean(string="Active", default=True, tracking=True)
