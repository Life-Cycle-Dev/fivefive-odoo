from odoo import models, fields

class ProductProduct(models.Model):
    _name = "five.five.product.product"
    _description = "Product"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Name", required=True, tracking=True)
    image = fields.Image(string="Product Image", max_width=1920, max_height=1920, tracking=True)
    unit_id = fields.Many2one(
        "five.five.product.unit",
        string="Unit",
        tracking=True,
    )
    variance_ids = fields.One2many(
        "five.five.product.variance",
        "product_id",
        string="Product Variances",
        context={"active_test": False},
        tracking=True,
    )

    active = fields.Boolean(string="Active", default=True, tracking=True)
