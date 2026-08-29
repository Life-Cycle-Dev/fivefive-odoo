from odoo import SUPERUSER_ID, api
from odoo.tools.float_utils import float_is_zero


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    StoreInventory = env["five.five.store.inventory"]
    for inventory in StoreInventory.with_context(active_test=False).search([]):
        if float_is_zero(inventory.total_weight or 0.0, precision_digits=6) and inventory.weight_per_qty:
            inventory.total_weight = (inventory.quantity or 0.0) * inventory.weight_per_qty
