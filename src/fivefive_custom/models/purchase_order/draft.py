from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

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
    _rec_name = "number"

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
    total_amount_usd = fields.Float(string="Total Amount (USD)", compute="_compute_total_amount", store=True)
    amount_paid_usd = fields.Float(string="Amount Paid (USD)", default=0.0)
    amount_paid_thb = fields.Float(string="Amount Paid (THB)", default=0.0)
    balance_amount_usd = fields.Float(string="Balance Amount (USD)", compute="_compute_balance_amount", store=True)

    supplier_name = fields.Char(string="Supplier Name")
    supplier_tax_id = fields.Char(string="Supplier Tax ID")
    supplier_contact = fields.Char(string="Supplier Contact")
    supplier_phone = fields.Char(string="Supplier Phone")
    supplier_account_name = fields.Char(string="Supplier Account Name")
    supplier_account_number = fields.Char(string="Supplier Account Number")
    supplier_account_bank_name = fields.Char(string="Supplier Bank Name")
    supplier_account_bank_address = fields.Char(string="Supplier Bank Address")
    supplier_account_bank_swift_code = fields.Char(string="Supplier Bank Swift Code")

    number = fields.Char(
        string="Number",
        required=True,
        readonly=True,
        copy=False,
        default="draft",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("po_issued", "Issued"),
            ("documents_completed", "Documents Completed"),
            ("clearing", "Clearing"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        tracking=True,
    )
    reason_cancel = fields.Text(string="Reason for Cancel")

    @api.model
    def _prepare_supplier_snapshot_values_for_supplier(self, supplier):
        if not supplier:
            return {name: "-" for name in _SUPPLIER_SNAPSHOT_FIELDS}
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
            if not vals.get("number") or vals.get("number") == "draft":
                vals["number"] = self.env["ir.sequence"].next_by_code("five.five.purchase.order")
                if not vals["number"]:
                    raise UserError("No sequence found for purchase orders (code: five.five.purchase.order). Update the module.")
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

    @api.depends("commercial_invoice_line_ids.total_price_usd")
    def _compute_total_amount(self):
        for record in self:
            record.total_amount_usd = sum(record.commercial_invoice_line_ids.mapped("total_price_usd"))

    @api.depends("total_amount_usd", "amount_paid_usd")
    def _compute_balance_amount(self):
        for record in self:
            record.balance_amount_usd = record.total_amount_usd - record.amount_paid_usd

    @api.constrains("total_amount_usd", "amount_paid_usd", "commercial_invoice_line_ids", "commercial_invoice_line_ids.total_price_usd")
    def _check_total_amount_not_less_than_amount_paid(self):
        for record in self:
            if float_compare(record.total_amount_usd, record.amount_paid_usd, precision_digits=2) < 0:
                raise UserError("ไม่สามารถอัปเดต Commercial Invoice Lines ได้ เพราะยอดรวมจะน้อยกว่า Amount Paid")

    def action_po_issue(self):
        for record in self:
            if record.state != "draft":
                raise UserError("เฉพาะ PO ที่อยู่ใน status Draft เท่านั้น ที่สามารถ Issue PO ได้ ไม่สามารถดำเนินการต่อได้")
            record.state = "po_issued"

            if record.state == "draft":
                number = self.env["ir.sequence"].next_by_code("five.five.purchase.order")
                if not number:
                    raise UserError("No sequence found for purchase orders (code: five.five.purchase.order). Update the module.")

                record.number = number

        return True

    def action_cancel(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError("สามารถ Cancel PO ที่อยู่ใน status Draft เท่านั้น ไม่สามารถดำเนินการต่อได้")

        if self.amount_paid_usd > 0:
            raise UserError("ไม่สามารถ Cancel PO ที่มีการจ่ายเงินแล้วได้ กรุณาดำเนินการยกเลิกการจ่ายก่อนดำเนินการต่อ")

        return {
            "type": "ir.actions.act_window",
            "name": "ยกเลิก PO",
            "res_model": "five.five.purchase.order.cancel.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_purchase_order_id": self.id
            },
        }
