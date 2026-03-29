#!/bin/bash
set -e

envsubst < /etc/odoo/odoo.conf.template > /etc/odoo/odoo.conf

if [ "$SERVICE" = "migrator" ]; then
    echo "Running migration..."
    /usr/bin/odoo -c /etc/odoo/odoo.conf -d odoo -u fivefive_custom --without-demo=all --stop-after-init
else
    if [ "$DEBUG" = "1" ]; then
        echo "Starting Odoo with debug..."
        python3 /mnt/extra-addons/debug_connect.py
    else
        echo "Starting Odoo..."
        /usr/bin/odoo -c /etc/odoo/odoo.conf -d odoo --without-demo=all -u fivefive_custom
    fi
fi