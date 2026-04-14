from odoo import models, fields


class ProductCost(models.Model):
    _name = "five.five.product.cost"
    _description = "Product Cost"

    product_convert_id = fields.Many2one(
        "five.five.product.convert",
        string="Product Convert",
        required=True,
        ondelete="cascade",
    )

    cost_name = fields.Char(
        string="Cost Name",
        required=True,
    )

    cost = fields.Float(
        string="Cost/Qty (THB)",
        required=True,
        digits=(16, 2),
    )

    type = fields.Selection(
        selection=[
            ('fixed', 'Fixed'),
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('yearly', 'Yearly'),
        ],
        string="Cost Type",
        required=True,
    )
