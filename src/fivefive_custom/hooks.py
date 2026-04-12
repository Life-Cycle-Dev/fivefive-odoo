from odoo import SUPERUSER_ID, api


def post_init_hook(cr_or_env, registry=None):
    if registry is None:
        env = cr_or_env
    else:
        env = api.Environment(cr_or_env, SUPERUSER_ID, {})

    PurchaseOrder = env["five.five.purchase.order"]
    orders = PurchaseOrder.search(
        [("supplier_id", "!=", False), ("supplier_name", "=", False)]
    )
    for order in orders:
        order.with_context(mail_notrack=True).write(order._prepare_supplier_snapshot_values())
