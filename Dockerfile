FROM odoo:18

USER root
RUN apt-get update && \
    apt-get install -y gettext-base && \
    rm -rf /var/lib/apt/lists/*

COPY ./src /mnt/extra-addons

RUN chown -R odoo:odoo /mnt/extra-addons

USER odoo
