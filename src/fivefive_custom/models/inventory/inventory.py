from odoo import models, fields


class Inventory(models.Model):
    _name = "five.five.inventory"
    _description = "Inventory"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="Product Variant",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        "five.five.warehouse",
        string="Warehouse",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    lot_number = fields.Char(string="Lot Number", tracking=True)
    quantity = fields.Float(string="Quantity", tracking=True)
    quality_note = fields.Char(string="Quality Note", tracking=True)
