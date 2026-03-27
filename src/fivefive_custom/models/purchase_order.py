from odoo import models, fields

class PurchaseOrder(models.Model):
    _name = "five.five.purchase.order"

    name = fields.Char(string="Name", required=True)
    active = fields.Boolean(string="Active", default=True)