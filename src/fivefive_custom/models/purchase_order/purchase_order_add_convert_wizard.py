from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PurchaseOrderAddConvertWizard(models.TransientModel):
    _name = "five.five.purchase.order.add.convert.wizard"
    _description = "Add converted product without commercial invoice line"

    purchase_order_id = fields.Many2one(
        "five.five.purchase.order",
        string="Purchase Order",
        required=True,
        readonly=True,
    )
    product_variant_id = fields.Many2one(
        "five.five.product.variant",
        string="Product Variant",
    )
    size_id = fields.Many2one(
        "five.five.product.size",
        related="product_variant_id.size_id",
        string="Size",
        readonly=True,
    )
    size_name = fields.Char(
        string="Size",
        related="size_id.name",
        readonly=True,
    )
    quantity = fields.Float(string="Quantity", default=1.0)
    weight_per_qty = fields.Float(string="Weight per Qty")
    quality_note = fields.Char(string="Quality Note")
    quality_image = fields.Image(string="Quality Image", max_width=1920, max_height=1920)
    item_number = fields.Char(string="Item Number")
    container_number = fields.Char(string="Container No.")
    lot_number = fields.Char(string="Lot Number")
    convert_date = fields.Date(string="Date", default=fields.Date.context_today)
    brand_id = fields.Many2one("five.five.product.brand", string="Brand")
    description_id = fields.Many2one("five.five.product.description", string="Description")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        po_id = res.get("purchase_order_id") or self.env.context.get("default_purchase_order_id")
        if po_id:
            po = self.env["five.five.purchase.order"].browse(po_id)
            res["purchase_order_id"] = po.id
            if po.shipment_container_number:
                res.setdefault("container_number", po.shipment_container_number)
        return res

    def action_confirm(self):
        self.ensure_one()
        po = self.purchase_order_id
        if not po:
            raise UserError(_("Purchase Order not found."))
        if po.state == "closed":
            raise UserError(_("Cannot add converted products after the purchase order is closed."))
        if po.state != "clearing":
            raise UserError(_("Converted products can only be added while the PO is in Clearing."))
        if not self.product_variant_id:
            raise UserError(_("Please select a product variant."))
        if self.quantity <= 0:
            raise UserError(_("Quantity must be greater than zero."))
        if not (self.quality_note or "").strip():
            raise UserError(_("Quality Note is required."))
        if not (self.container_number or "").strip():
            raise UserError(_("Container No. is required."))

        self.env["five.five.product.convert"].create(
            {
                "purchase_order_id": po.id,
                "product_variant_id": self.product_variant_id.id,
                "quantity": self.quantity,
                "weight_per_qty": self.weight_per_qty,
                "quality_note": self.quality_note.strip(),
                "quality_image": self.quality_image,
                "item_number": self.item_number,
                "container_number": self.container_number.strip(),
                "lot_number": self.lot_number,
                "convert_date": self.convert_date,
                "brand_id": self.brand_id.id if self.brand_id else False,
                "description_id": self.description_id.id if self.description_id else False,
            }
        )
        return {"type": "ir.actions.act_window_close"}
