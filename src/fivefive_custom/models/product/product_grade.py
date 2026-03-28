from odoo import models, fields


class ProductGrade(models.Model):
    _name = "five.five.product.grade"
    _description = "Product Grade"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _sql_constraints = [
        ("five_five_product_grade_name_uniq", "unique(name)", "Grade name must be unique."),
    ]

    name = fields.Char(string="Name", required=True, tracking=True)
    active = fields.Boolean(string="Active", default=True, tracking=True)
