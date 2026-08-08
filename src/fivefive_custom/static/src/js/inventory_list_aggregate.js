/** @odoo-module **/

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ListRenderer } from "@web/views/list/list_renderer";
import { onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

const formatters = registry.category("formatters");
const INVENTORY_LIST_CLASS = "ff_five_five_inventory_list";

function isInventoryList(archInfo) {
    const cls = archInfo?.className;
    if (!cls || typeof cls !== "string") {
        return false;
    }
    return cls.trim().split(/\s+/).includes(INVENTORY_LIST_CLASS);
}

function formatQuantityAggregate(renderer, aggregateValue) {
    const column = renderer.allColumns.find((col) => col.name === "quantity");
    if (!column) {
        return aggregateValue;
    }
    const field = renderer.fields.quantity;
    const { attrs, widget } = column;
    const formatter = formatters.get(widget, false) || formatters.get(field.type, false);
    const formatOptions = {
        digits: attrs.digits ? JSON.parse(attrs.digits) : undefined,
        escape: true,
    };
    return formatter ? formatter(aggregateValue, formatOptions) : aggregateValue;
}

const aggregatesDescriptor = Object.getOwnPropertyDescriptor(ListRenderer.prototype, "aggregates");

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.serverQuantityTotal = useState({ value: null });
        if (isInventoryList(this.props.archInfo)) {
            onWillStart(() => this._fetchInventoryQuantityTotal(this.props));
            onWillUpdateProps((nextProps) => {
                if (isInventoryList(nextProps.archInfo)) {
                    return this._fetchInventoryQuantityTotal(nextProps);
                }
            });
        }
    },

    async _fetchInventoryQuantityTotal(props) {
        const list = props.list;
        if (list.isGrouped || (list.selection && list.selection.length)) {
            this.serverQuantityTotal.value = null;
            return;
        }
        const result = await this.orm.readGroup(
            list.resModel,
            list.domain,
            ["quantity:sum"],
            [],
            { context: list.context }
        );
        this.serverQuantityTotal.value = result.length ? result[0].quantity : 0;
    },

    get aggregates() {
        const aggregates = aggregatesDescriptor.get.call(this);
        if (
            !isInventoryList(this.props.archInfo) ||
            this.props.list.isGrouped ||
            (this.props.list.selection && this.props.list.selection.length) ||
            this.serverQuantityTotal.value === null ||
            !aggregates.quantity
        ) {
            return aggregates;
        }
        return {
            ...aggregates,
            quantity: {
                ...aggregates.quantity,
                value: formatQuantityAggregate(this, this.serverQuantityTotal.value),
            },
        };
    },
});
