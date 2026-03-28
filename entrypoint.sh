#!/bin/bash
set -e

envsubst < /etc/odoo/odoo.conf.template > /etc/odoo/odoo.conf

if [ "$SERVICE" = "migrator" ]; then
    echo "Running migration..."
    /usr/bin/odoo -c /etc/odoo/odoo.conf -d odoo -u fivefive_custom --without-demo=all --stop-after-init
else
    echo "Starting Odoo..."
    exec /usr/bin/odoo -c /etc/odoo/odoo.conf -d odoo --without-demo=all
fi
