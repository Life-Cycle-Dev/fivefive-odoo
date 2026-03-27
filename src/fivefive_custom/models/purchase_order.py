from odoo import api, models, fields

class PurchaseOrder(models.Model):
    _name = "five.five.purchase.order"
    _description = "Purchase Order (PO)"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    supplier = fields.Char(string="Supplier", required=True, tracking=True)
    commercial_invoice_line_ids = fields.One2many(
        "five.five.commercial.invoice.line",
        "purchase_order_id",
        string="Commercial Invoice Lines",
    )
    total_amount = fields.Float(string="Total Amount", compute="_compute_total_amount", store=True)
    amount_paid = fields.Float(string="Amount Paid", default=0.0)
    balance_amount = fields.Float(string="Balance Amount", compute="_compute_balance_amount", store=True)

    @api.depends("commercial_invoice_line_ids.total_price")
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = sum(record.commercial_invoice_line_ids.mapped("total_price"))

    @api.depends("total_amount", "amount_paid")
    def _compute_balance_amount(self):
        for record in self:
            record.balance_amount = record.total_amount - record.amount_paid