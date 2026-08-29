from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

from ..supplier import _default_country_id

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
    _order = "id desc"

    supplier_id = fields.Many2one(
        "five.five.supplier",
        string="Supplier",
        required=True,
        tracking=True,
        domain=[("active", "=", True)],
    )
    country_id = fields.Many2one(
        "res.country",
        string="Country",
        default=lambda self: _default_country_id(self.env),
        tracking=True,
    )
    commercial_invoice_line_ids = fields.One2many(
        "five.five.commercial.invoice.line",
        "purchase_order_id",
        string="Commercial Invoice Lines",
    )
    converted_product_ids = fields.One2many(
        "five.five.product.convert",
        "purchase_order_id",
        string="Converted Products",
    )
    total_amount_usd = fields.Float(string="Total Amount (USD)", compute="_compute_total_amount", store=True)
    amount_recorded_usd = fields.Float(string="Amount Recorded (USD)", default=0.0)
    amount_recorded_thb = fields.Float(string="Amount Recorded (THB)", default=0.0)
    amount_paid_usd = fields.Float(string="Amount Paid (USD)", default=0.0)
    amount_paid_thb = fields.Float(string="Amount Paid (THB)", default=0.0)
    balance_amount_usd = fields.Float(string="Balance Amount (USD)", compute="_compute_balance_amount", store=True)
    is_payment_recorded_complete = fields.Boolean(
        string="Payment Recorded Complete",
        compute="_compute_payment_completion_flags",
        store=True,
    )
    exchange_rate_thb_per_usd = fields.Float(
        string="Rate (THB/USD)",
        compute="_compute_exchange_rate_thb_per_usd",
        store=False,
        digits=(16, 6),
    )
    is_thailand_po = fields.Boolean(
        string="Thailand PO",
        compute="_compute_is_thailand_po",
        store=True,
    )
    currency_label = fields.Char(
        string="Currency Label",
        compute="_compute_currency_label",
    )

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
    supplier_credit_wizard_skipped = fields.Boolean(string="Supplier Credit Wizard Skipped", default=False)
    supplier_credit_applied = fields.Boolean(
        string="Supplier Credit Applied",
        compute="_compute_supplier_credit_applied",
        store=True,
    )
    has_supplier_credit_available = fields.Boolean(
        string="Has Supplier Credit Available",
        compute="_compute_has_supplier_credit_available",
    )

    @api.depends("payment_ids.supplier_credit_id")
    def _compute_supplier_credit_applied(self):
        for record in self:
            record.supplier_credit_applied = bool(record.payment_ids.filtered("supplier_credit_id"))

    @api.depends(
        "supplier_id",
        "state",
        "supplier_credit_wizard_skipped",
        "supplier_credit_applied",
        "total_amount_usd",
        "amount_recorded_usd",
    )
    def _compute_has_supplier_credit_available(self):
        Credit = self.env["five.five.supplier.credit"]
        for record in self:
            record.has_supplier_credit_available = bool(record._get_supplier_credit_wizard_action())

    @api.model
    def _prepare_supplier_snapshot_values_for_supplier(self, supplier):
        if not supplier:
            return {
                **{name: "-" for name in _SUPPLIER_SNAPSHOT_FIELDS},
                "country_id": _default_country_id(self.env),
            }
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
            "country_id": supplier.country_id.id or _default_country_id(self.env),
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
        if "supplier_id" in vals:
            vals["supplier_credit_wizard_skipped"] = False
        res = super().write(vals)
        if "supplier_id" in vals:
            for rec in self:
                if rec.supplier_id:
                    rec.write(rec._prepare_supplier_snapshot_values())
        return res

    def action_try_open_supplier_credit_wizard(self):
        self.ensure_one()
        action = self._get_supplier_credit_wizard_action()
        return action or False

    def _build_supplier_credit_wizard_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Apply Supplier Credit"),
            "res_model": "five.five.supplier.credit.apply.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_purchase_order_id": self.id,
            },
        }

    def _get_supplier_credit_wizard_action(self):
        self.ensure_one()
        if (
            self.state not in ("draft", "po_issued")
            or not self.supplier_id
            or self.supplier_credit_wizard_skipped
            or self.supplier_credit_applied
        ):
            return False

        available = self.env["five.five.supplier.credit"]._get_available_amount(
            self.supplier_id,
            use_thb=self.is_thailand_po,
        )
        if float_compare(available, 0, precision_digits=2) <= 0:
            return False

        remaining_po = self.total_amount_usd - self.amount_recorded_usd
        if float_compare(remaining_po, 0, precision_digits=2) <= 0:
            return False

        return self._build_supplier_credit_wizard_action()

    def action_open_supplier_credit_wizard(self):
        self.ensure_one()
        if self.state not in ("draft", "po_issued"):
            raise UserError(_("Supplier credit can only be applied on draft or issued POs."))
        if not self.supplier_id:
            raise UserError(_("Please select a supplier first."))
        return self._build_supplier_credit_wizard_action()

    def _apply_supplier_credits(self, amount):
        self.ensure_one()
        Payment = self.env["five.five.purchase.order.payment"]
        Credit = self.env["five.five.supplier.credit"]
        use_thb = self.is_thailand_po
        credits = Credit._get_available_for_supplier(self.supplier_id, use_thb=use_thb)
        remaining_to_apply = amount

        for credit in credits:
            if float_compare(remaining_to_apply, 0, precision_digits=2) <= 0:
                break
            if use_thb:
                apply_thb = min(credit.remaining_thb, remaining_to_apply)
                apply_usd, apply_thb = credit._consume_thb(apply_thb)
                payment_amount_usd = apply_thb
                payment_amount_thb = apply_thb
            else:
                apply_usd = min(credit.remaining_usd, remaining_to_apply)
                apply_usd, apply_thb = credit._consume(apply_usd)
                payment_amount_usd = apply_usd
                payment_amount_thb = apply_thb
            payment = Payment.create(
                {
                    "purchase_order_id": self.id,
                    "amount_usd": payment_amount_usd,
                    "amount_thb": payment_amount_thb,
                    "pay_at": fields.Date.context_today(self),
                    "payment_status": "paid",
                    "note": _("Deducted from %s") % credit._get_source_label(),
                    "supplier_credit_id": credit.id,
                }
            )
            payment._recompute_purchase_order_payment_summary(self)
            remaining_to_apply -= apply_thb if use_thb else apply_usd

        if float_compare(remaining_to_apply, 0, precision_digits=2) > 0:
            raise UserError(_("Could not apply the requested supplier credit amount."))

        return True

    @api.onchange("supplier_id")
    def _onchange_supplier_id(self):
        self.supplier_credit_wizard_skipped = False
        if self.supplier_id:
            self.update(self._prepare_supplier_snapshot_values_for_supplier(self.supplier_id))
        else:
            self.update(
                {
                    **{name: False for name in _SUPPLIER_SNAPSHOT_FIELDS},
                    "country_id": _default_country_id(self.env),
                }
            )

    @api.depends("commercial_invoice_line_ids.total_price_usd")
    def _compute_total_amount(self):
        for record in self:
            record.total_amount_usd = sum(record.commercial_invoice_line_ids.mapped("total_price_usd"))

    @api.depends("total_amount_usd", "amount_paid_usd")
    def _compute_balance_amount(self):
        for record in self:
            record.balance_amount_usd = record.total_amount_usd - record.amount_paid_usd

    @api.depends("total_amount_usd", "amount_recorded_usd")
    def _compute_payment_completion_flags(self):
        for record in self:
            record.is_payment_recorded_complete = (
                float_compare(
                    record.amount_recorded_usd,
                    record.total_amount_usd,
                    precision_digits=2,
                )
                == 0
                and float_compare(record.total_amount_usd, 0, precision_digits=2) > 0
            )

    @api.depends("country_id")
    def _compute_is_thailand_po(self):
        thailand = self.env.ref("base.th", raise_if_not_found=False)
        for record in self:
            record.is_thailand_po = bool(thailand and record.country_id == thailand)

    @api.depends("is_thailand_po")
    def _compute_currency_label(self):
        for record in self:
            record.currency_label = "THB" if record.is_thailand_po else "USD"

    @api.depends("amount_recorded_thb", "amount_recorded_usd")
    def _compute_exchange_rate_thb_per_usd(self):
        for record in self:
            if record.amount_recorded_usd:
                record.exchange_rate_thb_per_usd = record.amount_recorded_thb / record.amount_recorded_usd
            else:
                record.exchange_rate_thb_per_usd = 0.0

    @api.constrains(
        "total_amount_usd",
        "amount_recorded_usd",
        "commercial_invoice_line_ids",
        "commercial_invoice_line_ids.total_price_usd",
    )
    def _check_total_amount_not_less_than_amount_paid(self):
        for record in self:
            if float_compare(record.total_amount_usd, record.amount_recorded_usd, precision_digits=2) < 0:
                raise UserError("ไม่สามารถอัปเดต Commercial Invoice Lines ได้ เพราะยอดรวมจะน้อยกว่า Amount Recorded")

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

        if len(self) == 1:
            wizard_action = self.action_try_open_supplier_credit_wizard()
            if wizard_action:
                return wizard_action
        return True

    def action_cancel(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError("สามารถ Cancel PO ที่อยู่ใน status Draft เท่านั้น ไม่สามารถดำเนินการต่อได้")

        if self.amount_recorded_usd > 0:
            raise UserError("ไม่สามารถ Cancel PO ที่มีการบันทึก Payment แล้วได้ กรุณาดำเนินการยกเลิกการจ่ายก่อนดำเนินการต่อ")

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
