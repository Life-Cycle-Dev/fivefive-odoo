/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";
import { onMounted, onPatched } from "@odoo/owl";

const MIN_HEADER_WIDTH_PX = 72;
const HEADER_CHAR_WIDTH_PX = 9;
const HEADER_PADDING_PX = 28;

function ffHeaderMinWidth(th) {
    const titleEl = th.querySelector(".o_column_title") || th;
    const text = (titleEl.textContent || "").trim();
    return Math.max(text.length * HEADER_CHAR_WIDTH_PX + HEADER_PADDING_PX, MIN_HEADER_WIDTH_PX);
}

function ffExpandListHeaders(tableEl, columns) {
    if (!tableEl) {
        return;
    }

    tableEl.style.setProperty("table-layout", "auto", "important");
    tableEl.style.setProperty("width", "100%", "important");

    const widthByField = {};
    for (const column of columns || []) {
        const width = column?.attrs?.width;
        if (column?.name && width) {
            widthByField[column.name] = width;
        }
    }

    for (const col of tableEl.querySelectorAll("colgroup col")) {
        col.style.removeProperty("width");
        col.style.setProperty("width", "auto", "important");
    }

    for (const th of tableEl.querySelectorAll("thead th")) {
        if (th.classList.contains("o_list_controller")) {
            continue;
        }

        const fieldName = th.getAttribute("data-name");
        const archWidth = fieldName ? widthByField[fieldName] : null;
        const minWidth = archWidth
            ? parseInt(archWidth, 10) || ffHeaderMinWidth(th)
            : ffHeaderMinWidth(th);
        th.style.setProperty("width", `${minWidth}px`, "important");
        th.style.setProperty("min-width", `${minWidth}px`, "important");
        th.style.setProperty("max-width", "none", "important");
        th.style.setProperty("white-space", "nowrap", "important");
        th.style.setProperty("overflow", "visible", "important");
        th.removeAttribute("title");

        for (const el of th.querySelectorAll(".o_column_title, .text-truncate, span, div")) {
            el.classList.remove("text-truncate");
            el.style.setProperty("white-space", "nowrap", "important");
            el.style.setProperty("overflow", "visible", "important");
            el.style.setProperty("text-overflow", "clip", "important");
            el.style.setProperty("max-width", "none", "important");
            el.style.setProperty("width", "auto", "important");
            el.removeAttribute("title");
        }
    }

    for (const td of tableEl.querySelectorAll("tbody td.o_data_cell")) {
        const fieldName = td.getAttribute("data-name");
        const archWidth = fieldName ? widthByField[fieldName] : null;
        if (!archWidth) {
            continue;
        }
        const minWidth = parseInt(archWidth, 10);
        if (!minWidth) {
            continue;
        }
        td.style.setProperty("min-width", `${minWidth}px`, "important");
        td.style.setProperty("overflow", "visible", "important");
        td.style.setProperty("text-overflow", "clip", "important");
    }
}

function ffScheduleExpandListHeaders(tableEl, columns) {
    if (!tableEl) {
        return;
    }
    ffExpandListHeaders(tableEl, columns);
    requestAnimationFrame(() => ffExpandListHeaders(tableEl, columns));
}

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => ffScheduleExpandListHeaders(this.tableRef?.el, this.allColumns));
        onPatched(() => ffScheduleExpandListHeaders(this.tableRef?.el, this.allColumns));
    },
});
