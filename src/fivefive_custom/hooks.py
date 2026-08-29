from odoo import SUPERUSER_ID, api

MIGRATION_TABLE = "ff_brand_description_migration"

MIGRATION_SOURCES = (
    ("five_five_product_convert", "five.five.product.convert"),
    ("five_five_inventory", "five.five.inventory"),
    ("five_five_store_inventory", "five.five.store.inventory"),
)


def pre_init_hook(cr):
    cr.execute(
        """
        CREATE TABLE IF NOT EXISTS ff_brand_description_migration (
            table_name VARCHAR,
            res_id INTEGER,
            brand VARCHAR,
            description TEXT
        )
        """
    )
    cr.execute(f"DELETE FROM {MIGRATION_TABLE}")

    for table_name, _model in MIGRATION_SOURCES:
        cr.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'brand'
            """,
            (table_name,),
        )
        if not cr.fetchone():
            continue
        cr.execute(
            f"""
            INSERT INTO {MIGRATION_TABLE} (table_name, res_id, brand, description)
            SELECT %s, id, brand, description
            FROM {table_name}
            WHERE COALESCE(brand, '') != '' OR COALESCE(description, '') != ''
            """,
            (table_name,),
        )


def _get_or_create_master(env, model_name, value):
    name = (value or "").strip()
    if not name:
        return False
    Model = env[model_name]
    record = Model.search([("name", "=", name)], limit=1)
    if not record:
        record = Model.create({"name": name})
    return record


def _migrate_brand_description(env):
    cr = env.cr
    cr.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = %s
        )
        """,
        (MIGRATION_TABLE,),
    )
    if not cr.fetchone()[0]:
        return

    cr.execute(
        f"SELECT table_name, res_id, brand, description FROM {MIGRATION_TABLE}"
    )
    rows = cr.fetchall()
    if not rows:
        cr.execute(f"DROP TABLE IF EXISTS {MIGRATION_TABLE}")
        return

    model_map = dict(MIGRATION_SOURCES)
    for table_name, res_id, brand, description in rows:
        model = model_map.get(table_name)
        if not model:
            continue
        record = env[model].browse(res_id).exists()
        if not record:
            continue
        vals = {}
        brand_rec = _get_or_create_master(env, "five.five.product.brand", brand)
        if brand_rec:
            vals["brand_id"] = brand_rec.id
        description_rec = _get_or_create_master(
            env, "five.five.product.description", description
        )
        if description_rec:
            vals["description_id"] = description_rec.id
        if vals:
            record.with_context(mail_notrack=True).write(vals)

    cr.execute(f"DROP TABLE IF EXISTS {MIGRATION_TABLE}")


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

    _migrate_brand_description(env)
