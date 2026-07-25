from odoo import models, fields

class Store(models.Model):
    _name = 'five.five.store'
    _description = 'Store'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Name", required=True, tracking=True)
    address = fields.Char(string="Address", tracking=True)
    phone = fields.Char(string="Phone", tracking=True)
    image = fields.Image(string="Image", max_width=1920, max_height=1920)
    pos_user_ids = fields.One2many(
        "five.five.store.pos.user",
        "store_id",
        string="POS Users",
    )
    
    active = fields.Boolean(string="Active", default=True, tracking=True)

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