from odoo import SUPERUSER_ID, api

from odoo.addons.fivefive_custom.hooks import _migrate_brand_description


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _migrate_brand_description(env)
