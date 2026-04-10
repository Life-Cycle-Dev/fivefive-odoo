import base64
import io
import secrets

from odoo import api, models, fields
from odoo.exceptions import UserError


class ProductVariant(models.Model):
    _name = "five.five.product.variant"
    _description = "Product variant"
    _rec_name = "name"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _sql_constraints = [
        ("five_five_product_variant_sku_uniq", "unique(sku)", "SKU must be unique."),
        ("five_five_product_variant_barcode_uniq", "unique(barcode)", "Barcode must be unique."),
    ]

    name = fields.Char(
        string="Name",
        compute="_compute_name",
        store=True,
        tracking=True,
    )
    sku = fields.Char(
        string="SKU",
        tracking=True
    )
    product_id = fields.Many2one(
        "five.five.product.product",
        string="Product",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    size_id = fields.Many2one(
        "five.five.product.size",
        required=True,
        string="Size",
        tracking=True,
    )
    grade_id = fields.Many2one(
        "five.five.product.grade",
        string="Grade",
        required=True,
        tracking=True,
    )
    image = fields.Image(
        string="Image",
        max_width=1920,
        max_height=1920
    )
    product_name = fields.Char(
        string="Product Name",
        compute="_compute_product_name",
        store=True,
    )

    barcode = fields.Char(
        string="Barcode",
        tracking=True
    )
    barcode_image = fields.Image(
        string="Barcode Image",
        compute="_compute_barcode_image",
        store=True,
    )

    active = fields.Boolean(string="Active", default=True, tracking=True)

    def _generate_unique_sku(self):
        for _ in range(200):
            candidate = str(secrets.randbelow(5 ** 5)).zfill(5)
            sku = f"product-sku-{candidate}"
            if not self.search_count([("sku", "=", sku)]):
                return sku
        raise UserError("Could not generate a unique sku. Please try again.")

    def _generate_barcode(self):
        for _ in range(200):
            candidate = str(secrets.randbelow(10**10)).zfill(10)
            if not self.search_count([("barcode", "=", candidate)]):
                return candidate
        raise UserError("Could not generate a unique barcode. Please try again.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            sku = (vals.get("sku") or "").strip()
            if not sku:
                vals["sku"] = self._generate_unique_sku()
            barcode = (vals.get("barcode") or "").strip()
            if not barcode:
                vals["barcode"] = self._generate_barcode()
            if not vals.get("image"):
                product_id = vals.get("product_id")
                if product_id:
                    product = self.env["five.five.product.product"].browse(product_id)
                    if product and product.image:
                        vals["image"] = product.image
        return super().create(vals_list)

    def write(self, vals):
        if "barcode" in vals:
            barcode = (vals.get("barcode") or "").strip()
            if not barcode:
                vals["barcode"] = self._generate_barcode()
        return super().write(vals)

    @api.depends("size_id.name", "product_id.name", "grade_id.name")
    def _compute_name(self):
        for rec in self:
            parts = []
            if rec.size_id:
                parts.append(str(rec.size_id.name).strip())
            if rec.product_id:
                parts.append((rec.product_id.name or "").strip())
            if rec.grade_id:
                parts.append((rec.grade_id.name or "").strip())
            rec.name = "".join(p for p in parts if p)

    @api.depends("product_id.name")
    def _compute_product_name(self):
        for rec in self:
            rec.product_name = (rec.product_id.name or "").strip() if rec.product_id else ""

    def _barcode_png_bytes(self, value):
        try:
            from barcode import Code128
            from barcode.writer import ImageWriter

            buf = io.BytesIO()
            Code128(value, writer=ImageWriter()).write(
                buf,
                options={
                    "module_width": 0.35,
                    "module_height": 18.0,
                    "quiet_zone": 4.0,
                    "font_size": 10,
                    "text_distance": 7.0,
                },
            )
            return buf.getvalue()
        except Exception as e:
            raise e

    @api.depends("barcode")
    def _compute_barcode_image(self):
        for rec in self:
            value = (rec.barcode or "").strip()
            if not value:
                rec.barcode_image = False
                continue
            png = self._barcode_png_bytes(value)
            rec.barcode_image = base64.b64encode(png) if png else False

    def action_open_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Product variant",
            "res_model": "five.five.product.variant",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }
