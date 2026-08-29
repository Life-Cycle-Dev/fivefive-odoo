from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Variant = env["five.five.product.variant"]
    variants = Variant.with_context(active_test=False).search([])
    if variants:
        env.add_to_compute(Variant._fields["name"], variants)
