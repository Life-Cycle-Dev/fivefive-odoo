from odoo import api, models, fields

class CommercialInvoiceLine(models.Model):
    _name = "five.five.commercial.invoice.line"
    _description = "Commercial Invoice Line"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        ondelete="cascade",
        index=True,
    )

    name = fields.Char(string="Name", required=True)
    unit_id = fields.Many2one(
        "five.five.product.unit",
        string="Unit",
        required=True,
    )
    size_id = fields.Many2one(
        "five.five.product.size",
        required=True,
        string="Size",
    )
    grade_id = fields.Many2one(
        "five.five.product.grade",
        string="Grade",
        required=True,
    )
    unit_price = fields.Float(string="Unit Price", required=True)
    quantity = fields.Float(string="Quantity", required=True)
    total_price = fields.Float(string="Total Price", compute="_compute_total_price", store=True)

    @api.depends("unit_price", "quantity")
    def _compute_total_price(self):
        for line in self:
            line.total_price = line.quantity * line.unit_price