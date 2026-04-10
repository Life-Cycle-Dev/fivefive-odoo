from odoo import SUPERUSER_ID, api


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    PurchaseOrder = env["five.five.purchase.order"]
    orders = PurchaseOrder.search(
        [("supplier_id", "!=", False), ("supplier_name", "=", False)]
    )
    for order in orders:
        order.with_context(mail_notrack=True).write(order._prepare_supplier_snapshot_values())
