from odoo import api, fields, models


class Store(models.Model):
    _name = 'five.five.store'
    _description = 'Store'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Name", required=True, tracking=True)
    branch_subtitle = fields.Char(
        string="Branch Subtitle",
        tracking=True,
        help="Optional second line on receipt header, e.g. mall or location name.",
    )
    receipt_company_name = fields.Char(
        string="Receipt Company Name",
        tracking=True,
        help="Legal company name printed on POS receipts.",
    )
    branch_code = fields.Char(
        string="Branch Code",
        tracking=True,
        help="Branch number shown on receipt header and POS ID.",
    )
    tax_id = fields.Char(string="Tax ID", tracking=True)
    address = fields.Text(string="Address", tracking=True)
    phone = fields.Char(string="Phone", tracking=True)
    pos_vat_included = fields.Boolean(
        string="VAT Included on Receipt",
        tracking=True,
        default=False,
        help="When enabled, receipt title becomes abbreviated tax invoice and shows VAT breakdown.",
    )
    pos_vat_percent = fields.Float(
        string="VAT %",
        tracking=True,
        default=7.0,
        help="VAT rate used on receipt when VAT is included.",
    )
    image = fields.Image(string="Image", max_width=1920, max_height=1920)
    pos_user_ids = fields.One2many(
        "five.five.store.pos.user",
        "store_id",
        string="POS Users",
    )
    
    active = fields.Boolean(string="Active", default=True, tracking=True)

    @api.model
    def _default_receipt_company_name(self):
        return self.env.company.name

    @api.model
    def _default_tax_id(self):
        return self.env.company.vat or ""

    @api.model
    def _default_address(self):
        company = self.env.company
        parts = [
            part
            for part in [
                company.street,
                company.street2,
                company.city,
                company.state_id.name if company.state_id else "",
                company.zip,
            ]
            if part
        ]
        return "\n".join(parts)

    @api.model
    def _default_pos_vat_included(self):
        company = self.env.company
        if "pos_vat_included" in company._fields:
            return company.pos_vat_included
        return False

    @api.model
    def _default_pos_vat_percent(self):
        company = self.env.company
        if "pos_vat_percent" in company._fields:
            return company.pos_vat_percent
        return 7.0

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if "receipt_company_name" in fields_list and "receipt_company_name" not in defaults:
            defaults["receipt_company_name"] = self._default_receipt_company_name()
        if "tax_id" in fields_list and "tax_id" not in defaults:
            defaults["tax_id"] = self._default_tax_id()
        if "address" in fields_list and "address" not in defaults:
            defaults["address"] = self._default_address()
        if "pos_vat_included" in fields_list and "pos_vat_included" not in defaults:
            defaults["pos_vat_included"] = self._default_pos_vat_included()
        if "pos_vat_percent" in fields_list and "pos_vat_percent" not in defaults:
            defaults["pos_vat_percent"] = self._default_pos_vat_percent()
        return defaults

    def get_pos_receipt_settings(self):
        self.ensure_one()
        return {
            "store_name": self.name or "",
            "branch_subtitle": self.branch_subtitle or "",
            "company_name": self.receipt_company_name or self.env.company.name or "",
            "branch_code": self.branch_code or "",
            "address": self.address or "",
            "tax_id": self.tax_id or self.env.company.vat or "",
            "phone": self.phone or "",
            "vat_included": bool(self.pos_vat_included),
            "vat_percent": self.pos_vat_percent or 0.0,
        }

    def toggle_active(self):
        for record in self:
            record.active = not record.active

    def action_open_pos(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/pos",
            "target": "new",
        }