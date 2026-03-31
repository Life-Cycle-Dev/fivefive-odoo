from odoo import models,fields


class InventMoment(models.Model):
    _name = "five.five.invent.moment"
    _description = "Invent Moment"
    _inherit = ["mail.thread","mail.activity.mixin"]

    product = fields.Many2one(
        "five.five.product.product",
        string = "Product",
        required = True,
        ondelete  = "cascade",
        tracking = True
    )
    warehouse = fields.Many2one(
        "five.five.warehouse",
        string = "Warehouse",
        required = True,
        ondelete  = "cascade",
        tracking = True
    )
    lot_number = fields.Char(
        string = "Lot Number",
        tracking = True
    )
    store = fields.Many2one(
        "five.five.store",
        string = "Store",
        tracking = True
    )
    qty = fields.Float(string="Quantity", tracking=True)
    status = fields.Selection([
        ('deduct', 'Deduct Stock'),
        ('no_deduct', 'Do Not Deduct Stock'),
    ], string="Status", default='no_deduct')

