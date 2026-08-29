from odoo.addons.fivefive_custom.hooks import pre_init_hook


def migrate(cr, version):
    pre_init_hook(cr)
