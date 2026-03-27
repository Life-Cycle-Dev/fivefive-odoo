from odoo import models, fields

class ProductVariance(models.Model):
    _name = "five.five.product.variance"
    _description = "Product Variance"
    _rec_name = "sku"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _sql_constraints = [
        ("five_five_product_variance_sku_uniq", "unique(sku)", "SKU must be unique."),
    ]

    sku = fields.Char(string="SKU", required=True, tracking=True)
    product_id = fields.Many2one(
        "five.five.product.product",
        string="Product",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    size = fields.Float(string="Size", tracking=True)
    grade_id = fields.Many2one(
        "five.five.product.grade",
        string="Grade",
        tracking=True,
    )

    active = fields.Boolean(string="Active", default=True, tracking=True)

    def action_open_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Product Variance",
            "res_model": "five.five.product.variance",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }
