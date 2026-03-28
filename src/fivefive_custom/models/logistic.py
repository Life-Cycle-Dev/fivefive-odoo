from odoo import models, fields


class Logistic(models.Model):
    _name = "five.five.logistic"
    _description = "Logistic"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Name", required=True, tracking=True)
    contact = fields.Char(string="Contact", tracking=True)
    phone = fields.Char(string="Phone", tracking=True)
    image = fields.Image(string="Image", max_width=1920, max_height=1920, tracking=True)

    active = fields.Boolean(string="Active", default=True, tracking=True)
