from odoo import api, fields, models

_SUPPLIER_SNAPSHOT_FIELDS = (
    "supplier_name",
    "supplier_tax_id",
    "supplier_contact",
    "supplier_phone",
    "supplier_account_name",
    "supplier_account_number",
    "supplier_account_bank_name",
    "supplier_account_bank_address",
    "supplier_account_bank_swift_code",
)


class PurchaseOrder(models.Model):
    _name = "five.five.purchase.order"
    _description = "Purchase Order (PO)"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    supplier_id = fields.Many2one(
        "five.five.supplier",
        string="Supplier",
        required=True,
        tracking=True,
        domain=[("active", "=", True)],
    )
    commercial_invoice_line_ids = fields.One2many(
        "five.five.commercial.invoice.line",
        "purchase_order_id",
        string="Commercial Invoice Lines",
    )
    total_amount = fields.Float(string="Total Amount", compute="_compute_total_amount", store=True)
    amount_paid = fields.Float(string="Amount Paid", default=0.0)
    balance_amount = fields.Float(string="Balance Amount", compute="_compute_balance_amount", store=True)

    supplier_name = fields.Char(string="Supplier Name")
    supplier_tax_id = fields.Char(string="Supplier Tax ID")
    supplier_contact = fields.Char(string="Supplier Contact")
    supplier_phone = fields.Char(string="Supplier Phone")
    supplier_account_name = fields.Char(string="Supplier Account Name")
    supplier_account_number = fields.Char(string="Supplier Account Number")
    supplier_account_bank_name = fields.Char(string="Supplier Bank Name")
    supplier_account_bank_address = fields.Char(string="Supplier Bank Address")
    supplier_account_bank_swift_code = fields.Char(string="Supplier Bank Swift Code")

    @api.model
    def _prepare_supplier_snapshot_values_for_supplier(self, supplier):
        if not supplier:
            return {name: False for name in _SUPPLIER_SNAPSHOT_FIELDS}
        return {
            "supplier_name": supplier.name or "-",
            "supplier_tax_id": supplier.tax_id or "-",
            "supplier_contact": supplier.contact or "-",
            "supplier_phone": supplier.phone or "-",
            "supplier_account_name": supplier.account_name or "-",
            "supplier_account_number": supplier.account_number or "-",
            "supplier_account_bank_name": supplier.account_bank_name or "-",
            "supplier_account_bank_address": supplier.account_bank_address or "-",
            "supplier_account_bank_swift_code": supplier.account_bank_swift_code or "-",
        }

    def _prepare_supplier_snapshot_values(self):
        self.ensure_one()
        return self._prepare_supplier_snapshot_values_for_supplier(self.supplier_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            supplier_id = vals.get("supplier_id")
            if supplier_id:
                supplier = self.env["five.five.supplier"].browse(supplier_id)
                vals.update(self._prepare_supplier_snapshot_values_for_supplier(supplier))
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if "supplier_id" in vals:
            for rec in self:
                if rec.supplier_id:
                    rec.write(rec._prepare_supplier_snapshot_values())
        return res

    @api.onchange("supplier_id")
    def _onchange_supplier_id(self):
        if self.supplier_id:
            self.update(self._prepare_supplier_snapshot_values_for_supplier(self.supplier_id))
        else:
            self.update({name: False for name in _SUPPLIER_SNAPSHOT_FIELDS})

    @api.depends("commercial_invoice_line_ids.total_price")
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = sum(record.commercial_invoice_line_ids.mapped("total_price"))

    @api.depends("total_amount", "amount_paid")
    def _compute_balance_amount(self):
        for record in self:
            record.balance_amount = record.total_amount - record.amount_paid
