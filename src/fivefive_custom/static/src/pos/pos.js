(() => {
    "use strict";

    const STORAGE_KEY = "ff_pos_auth";

    const state = {
        token: null,
        user: null,
        session: null,
        products: [],
        cart: [],
        discountType: "percent",
        discountValue: 0,
        amountPaidInput: "",
        paymentMethod: "cash",
        transferSlip: null,
        orderNote: "",
        search: "",
        requisitionProducts: [],
        requisitionCart: [],
        requisitionSearch: "",
        requisitions: [],
        selectedRequisition: null,
        stockSearch: "",
        cancelOrderId: null,
        salesOrders: [],
        selectedSalesOrder: null,
        stockSummary: [],
        lastOrder: null,
        lastReceipt: null,
    };

    let barcodeScanner = null;
    let barcodeScannerActive = false;
    let barcodeScannerMode = "pos";

    const PAGE_SIZE = 20;

    let pendingPayAfterSlip = false;

    const listState = {
        products: { page: 1 },
        requisitionProducts: { page: 1 },
        stock: { page: 1 },
        sales: { page: 1 },
        requisitions: { page: 1 },
    };

    const paginationMeta = {
        products: { page: 1, total: 0, totalPages: 1 },
        requisitionProducts: { page: 1, total: 0, totalPages: 1 },
        stock: { page: 1, total: 0, totalPages: 1 },
        sales: { page: 1, total: 0, totalPages: 1 },
        requisitions: { page: 1, total: 0, totalPages: 1 },
    };

    const dateFilters = {
        sales: { date: "" },
        requisitions: { date: "" },
    };

    function todayDateInputValue() {
        const now = new Date();
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, "0");
        const day = String(now.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    function getDateFilterRange(key) {
        const date = dateFilters[key].date;
        if (!date) {
            return { from: null, to: null };
        }
        return { from: date, to: date };
    }

    function debounce(fn, delay = 300) {
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn(...args), delay);
        };
    }

    function applyPaginationMeta(key, data) {
        const meta = data?.pagination || {};
        paginationMeta[key] = {
            page: meta.page || 1,
            total: meta.total || 0,
            totalPages: meta.total_pages || 1,
        };
        listState[key].page = paginationMeta[key].page;
    }

    function renderPaginationBar(key, containerId) {
        const el = document.getElementById(containerId);
        if (!el) return;
        const meta = paginationMeta[key];
        if (!meta.total) {
            el.innerHTML = "";
            el.hidden = true;
            return;
        }
        el.hidden = false;
        el.innerHTML = `
            <button type="button" class="pos-page-btn" data-page-key="${key}" data-page-action="prev" ${meta.page <= 1 ? "disabled" : ""} aria-label="หน้าก่อน">‹</button>
            <span class="pos-page-info">${meta.page} / ${meta.totalPages} (${formatQty(meta.total)} รายการ)</span>
            <button type="button" class="pos-page-btn" data-page-key="${key}" data-page-action="next" ${meta.page >= meta.totalPages ? "disabled" : ""} aria-label="หน้าถัดไป">›</button>
        `;
    }

    async function changePage(key, delta) {
        const meta = paginationMeta[key];
        const nextPage = meta.page + delta;
        if (nextPage < 1 || nextPage > meta.totalPages) return;
        listState[key].page = nextPage;
        const loaders = {
            products: loadProducts,
            requisitionProducts: loadRequisitionProducts,
            stock: loadStock,
            sales: loadSalesHistory,
            requisitions: loadRequisitionList,
        };
        await loaders[key]();
    }

    const orderStateLabels = {
        done: "สำเร็จ",
        cancelled: "ยกเลิก",
    };

    const paymentMethodLabels = {
        cash: "เงินสด",
        transfer: "โอนเงิน",
    };

    const stateLabels = {
        submitted: "รอจัดเตรียม",
        prepared: "จัดเตรียมแล้ว (รอรับ)",
        received: "รับแล้ว",
        done: "เสร็จสิ้น",
        cancelled: "ยกเลิก",
    };

    const screens = {
        login: document.getElementById("screen-login"),
        openSession: document.getElementById("screen-open-session"),
        pos: document.getElementById("screen-pos"),
        discount: document.getElementById("screen-discount"),
        payment: document.getElementById("screen-payment"),
        closeSession: document.getElementById("screen-close-session"),
        success: document.getElementById("screen-success"),
        requisition: document.getElementById("screen-requisition"),
        requisitionList: document.getElementById("screen-requisition-list"),
        requisitionDetail: document.getElementById("screen-requisition-detail"),
        stock: document.getElementById("screen-stock"),
        salesHistory: document.getElementById("screen-sales-history"),
        salesDetail: document.getElementById("screen-sales-detail"),
    };

    function formatDateTime(value) {
        if (!value) return "-";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return date.toLocaleString("th-TH", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function formatMoney(value) {
        return Number(value || 0).toLocaleString("th-TH", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function formatQty(value) {
        return Number(value || 0).toLocaleString("th-TH", {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        });
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function formatReceiptDate(value) {
        if (!value) return "-";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        const day = String(date.getDate()).padStart(2, "0");
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const year = String(date.getFullYear()).slice(-2);
        return `${day}/${month}/${year}`;
    }

    function formatReceiptTime(value) {
        if (!value) return "-";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        const hours = String(date.getHours()).padStart(2, "0");
        const minutes = String(date.getMinutes()).padStart(2, "0");
        return `${hours}:${minutes}`;
    }

    function mergeReceiptSettings(receipt) {
        const settings = receipt.receipt_settings || state.user?.receipt_settings || {};
        return {
            ...receipt,
            store_name: receipt.store_name || settings.store_name || "ร้านค้า",
            branch_subtitle: receipt.branch_subtitle ?? settings.branch_subtitle ?? "",
            company_name: receipt.company_name ?? settings.company_name ?? "",
            branch_code: receipt.branch_code ?? settings.branch_code ?? "",
            address: receipt.address ?? settings.address ?? "",
            tax_id: receipt.tax_id ?? settings.tax_id ?? "",
            vat_included: receipt.vat_included ?? settings.vat_included ?? false,
            vat_percent: Number(receipt.vat_percent ?? settings.vat_percent ?? 0),
        };
    }

    function buildReceiptHtml(receiptInput) {
        const receipt = mergeReceiptSettings(receiptInput || {});
        const settings = receipt;
        const vatIncluded = Boolean(settings.vat_included);
        const vatPercent = Number(settings.vat_percent || 0);
        const total = Number(receipt.total || 0);
        const beforeVat = vatIncluded && vatPercent > 0 ? total / (1 + vatPercent / 100) : total;
        const vatAmount = vatIncluded ? total - beforeVat : 0;
        const itemCount = (receipt.lines || []).reduce(
            (sum, line) => sum + Number(line.quantity || 0),
            0
        );
        const branchCode = settings.branch_code || "00000";

        const linesHtml = (receipt.lines || [])
            .map((line) => {
                const qty = formatQty(line.quantity);
                const name = escapeHtml(line.product_name);
                const subtotal = formatMoney(line.subtotal);
                return `<div class="line-item"><span class="line-qty">${qty}</span><span class="line-name">${name}</span><span class="line-price">${subtotal}</span></div>`;
            })
            .join("");

        const branchNameHtml = settings.store_name
            ? `<div class="center branch-name">${escapeHtml(settings.store_name)}</div>`
            : settings.branch_subtitle
              ? `<div class="center branch-name">${escapeHtml(settings.branch_subtitle)}</div>`
              : "";
        const subtitleHtml =
            settings.store_name && settings.branch_subtitle
                ? `<div class="center subtitle">${escapeHtml(settings.branch_subtitle)}</div>`
                : "";
        const companyHtml = settings.company_name
            ? `<div class="center company">${escapeHtml(settings.company_name)}</div>`
            : "";
        const branchHtml = settings.branch_code
            ? `<div class="center branch">No. Branch : ${escapeHtml(branchCode)}</div>`
            : "";
        const addressHtml = settings.address
            ? `<div class="center address">${escapeHtml(settings.address)}</div>`
            : "";
        const taxIdHtml = settings.tax_id
            ? `<div class="center tax-id">TAX ID : ${escapeHtml(settings.tax_id)}</div>`
            : "";

        const titleHtml = vatIncluded
            ? `<div class="center title-en">Receipt / TAX Invoice (ABB)</div>
               <div class="center vat-label">VAT Included</div>`
            : `<div class="center title">ใบเสร็จรับเงิน / Receipt</div>`;

        const discountRow =
            Number(receipt.discount_amount || 0) > 0
                ? `<div class="summary-row"><span>ส่วนลด</span><span>${formatMoney(receipt.discount_amount)}</span></div>`
                : "";

        const vatRows = vatIncluded
            ? `<div class="solid-divider"></div>
               <div class="summary-row"><span>Before VAT</span><span>${formatMoney(beforeVat)}</span></div>
               <div class="summary-row"><span>VAT ${formatQty(vatPercent)}%</span><span>${formatMoney(vatAmount)}</span></div>`
            : "";

        const noteHtml = receipt.note
            ? `<div class="note">หมายเหตุ: ${escapeHtml(receipt.note)}</div>`
            : "";

        return `<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="utf-8"/>
    <title>ใบเสร็จ ${escapeHtml(receipt.number || "")}</title>
    <style>
        @page { size: 80mm auto; margin: 4mm; }
        * { box-sizing: border-box; }
        body {
            width: 72mm;
            margin: 0 auto;
            font-family: "Noto Sans Thai", sans-serif;
            font-size: 12px;
            color: #000;
            line-height: 1.6;
        }
        .center { text-align: center; }
        .branch-name {
            font-size: 16px;
            font-weight: 700;
            margin: 0 0 6px;
            line-height: 1.45;
        }
        .subtitle, .company, .branch, .address, .tax-id {
            font-size: 11px;
            margin: 4px 0;
            line-height: 1.55;
        }
        .address { white-space: pre-line; }
        .title { font-size: 13px; font-weight: 700; margin: 0 0 4px; line-height: 1.5; }
        .title-en { font-size: 12px; font-weight: 700; margin: 8px 0 4px; line-height: 1.5; }
        .vat-label { font-size: 11px; font-weight: 600; margin: 0; line-height: 1.5; }
        .meta-row { display: flex; justify-content: space-between; gap: 8px; margin: 5px 0; line-height: 1.55; }
        .date-time-row span:last-child { text-align: right; }
        .divider { border-top: 1px dashed #000; margin: 10px 0; }
        .solid-divider { border-top: 2px solid #000; margin: 8px 0 6px; }
        .line-item { display: flex; gap: 8px; margin: 6px 0; align-items: flex-start; line-height: 1.55; }
        .line-qty { width: 18px; flex-shrink: 0; text-align: left; }
        .line-name { flex: 1; word-break: break-word; }
        .line-price { white-space: nowrap; text-align: right; }
        .items-count { margin: 6px 0 4px; font-size: 11px; line-height: 1.55; }
        .summary-row { display: flex; justify-content: space-between; gap: 8px; margin: 5px 0; line-height: 1.55; }
        .summary-row.grand {
            font-size: 14px;
            font-weight: 700;
            margin: 8px 0;
            border-bottom: 2px solid #000;
            padding: 6px 0;
            line-height: 1.5;
        }
        .note { margin-top: 8px; font-size: 11px; line-height: 1.55; }
        .thanks { margin-top: 14px; text-align: center; font-weight: 600; line-height: 1.55; }
    </style>
</head>
<body>
    ${branchNameHtml}
    ${subtitleHtml}
    ${companyHtml}
    ${branchHtml}
    ${addressHtml}
    ${taxIdHtml}
    ${titleHtml}
    <div class="divider"></div>
    <div class="meta-row"><span>POS ID:</span><span>${escapeHtml(branchCode)}</span></div>
    <div class="meta-row"><span>No. :</span><span>${escapeHtml(receipt.number || "-")}</span></div>
    <div class="meta-row date-time-row">
        <span>Date : ${escapeHtml(formatReceiptDate(receipt.order_date))}</span>
        <span>Time : ${escapeHtml(formatReceiptTime(receipt.order_date))}</span>
    </div>
    <div class="meta-row"><span>พนักงาน</span><span>${escapeHtml(receipt.cashier_name || "-")}</span></div>
    <div class="divider"></div>
    ${linesHtml}
    <div class="divider"></div>
    <div class="items-count">Items: ${formatQty(itemCount)}</div>
    <div class="summary-row"><span>รวม</span><span>${formatMoney(receipt.subtotal)}</span></div>
    ${discountRow}
    ${vatRows}
    <div class="summary-row grand"><span>Total</span><span>${formatMoney(receipt.total)}</span></div>
    ${noteHtml}
    <div class="thanks">ขอบคุณที่ใช้บริการ</div>
</body>
</html>`;
    }

    function printReceipt(receipt) {
        if (!receipt) return;
        let frame = document.getElementById("pos-receipt-print-frame");
        if (!frame) {
            frame = document.createElement("iframe");
            frame.id = "pos-receipt-print-frame";
            frame.setAttribute("aria-hidden", "true");
            frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
            document.body.appendChild(frame);
        }
        const doc = frame.contentWindow.document;
        doc.open();
        doc.write(buildReceiptHtml(receipt));
        doc.close();
        frame.contentWindow.focus();
        setTimeout(() => {
            frame.contentWindow.print();
        }, 250);
    }

    function saveAuth() {
        localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify({
                token: state.token,
                user: state.user,
                session: state.session,
            })
        );
    }

    function loadAuth() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return null;
            const data = JSON.parse(raw);
            if (!data?.token) return null;
            return data;
        } catch (_error) {
            return null;
        }
    }

    function isAuthError(message) {
        const text = (message || "").toLowerCase();
        return (
            text.includes("invalid or expired") ||
            text.includes("please login") ||
            text.includes("login again")
        );
    }

    function clearAuth() {
        localStorage.removeItem(STORAGE_KEY);
        state.token = null;
        state.user = null;
        state.session = null;
    }

    function showScreen(name) {
        Object.entries(screens).forEach(([key, element]) => {
            if (!element) return;
            element.classList.toggle("active", key === name);
        });
        if (name === "pos") {
            setTimeout(() => document.getElementById("barcode-input")?.focus(), 100);
        }
        if (name !== "pos" && name !== "requisition") {
            closeBarcodeScanner();
        }
    }

    function requisitionBadgeClass(state) {
        const classes = {
            submitted: "pos-badge-submitted",
            prepared: "pos-badge-prepared",
            received: "pos-badge-received",
            done: "pos-badge-done",
            cancelled: "pos-badge-cancelled",
        };
        return classes[state] || "pos-badge-submitted";
    }

    function showError(elementId, message) {
        const element = document.getElementById(elementId);
        if (!element) return;
        if (!message) {
            element.hidden = true;
            element.textContent = "";
            return;
        }
        element.hidden = false;
        element.textContent = message;
    }

    function showAlert(message, title = "แจ้งเตือน") {
        const modal = document.getElementById("pos-alert-modal");
        const titleEl = document.getElementById("pos-alert-title");
        const messageEl = document.getElementById("pos-alert-message");
        if (!modal || !messageEl) return;
        if (titleEl) titleEl.textContent = title;
        messageEl.textContent = message || "";
        modal.classList.add("show");
    }

    function hideAlertModal() {
        document.getElementById("pos-alert-modal")?.classList.remove("show");
    }

    async function rpc(route, params = {}) {
        const response = await fetch(route, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params,
                id: Date.now(),
            }),
        });
        const payload = await response.json();
        if (payload.error) {
            throw new Error(payload.error.data?.message || payload.error.message || "เกิดข้อผิดพลาด");
        }
        const result = payload.result;
        if (!result?.ok) {
            throw new Error(result?.error || "เกิดข้อผิดพลาด");
        }
        return result.data;
    }

    function computeSubtotal() {
        return state.cart.reduce((sum, line) => sum + line.unit_price * line.quantity, 0);
    }

    function computeDiscountAmount(subtotal) {
        const value = Number(state.discountValue || 0);
        if (value <= 0) return 0;
        if (state.discountType === "percent") {
            return subtotal * (Math.min(value, 100) / 100);
        }
        return Math.min(value, subtotal);
    }

    function computeTotals() {
        const subtotal = computeSubtotal();
        const discountAmount = computeDiscountAmount(subtotal);
        const total = subtotal - discountAmount;
        const amountPaid = Number(state.amountPaidInput || 0);
        const changeAmount = Math.max(amountPaid - total, 0);
        const itemQty = state.cart.reduce((sum, line) => sum + line.quantity, 0);
        return { subtotal, discountAmount, total, amountPaid, changeAmount, itemQty };
    }

    function cartRowHtml(line, editable) {
        const lineTotal = line.unit_price * line.quantity;
        const basePrice = line.base_unit_price ?? line.unit_price;
        const qtyCol = editable
            ? `<div class="pos-qty-stepper">
                <button type="button" class="pos-step-btn" data-action="dec" data-id="${line.id}">−</button>
                <span class="pos-qty-value">${formatQty(line.quantity)}</span>
                <button type="button" class="pos-step-btn" data-action="inc" data-id="${line.id}">+</button>
               </div>`
            : `<div class="pos-qty-readonly">${formatQty(line.quantity)}</div>`;
        const priceSub = editable
            ? `<div class="pos-cart-price-edit">
                <input
                    type="number"
                    class="pos-price-input"
                    data-price-id="${line.id}"
                    value="${line.unit_price}"
                    min="${basePrice}"
                    step="0.01"
                    inputmode="decimal"
                />
                <span class="pos-cart-price-hint">/ ชิ้น · ขั้นต่ำ ${formatMoney(basePrice)}</span>
               </div>`
            : `<div class="pos-cart-row-sub">${formatMoney(line.unit_price)} / ชิ้น</div>`;
        const removeCol = editable
            ? `<div class="pos-cart-remove">
                <button type="button" class="pos-remove-btn" data-action="remove" data-id="${line.id}" aria-label="ลบ">×</button>
               </div>`
            : "";
        return `
            <div class="pos-cart-row${editable ? " pos-cart-row--editable" : ""}">
                <div class="pos-cart-qty">${qtyCol}</div>
                <div class="pos-cart-info">
                    <div class="pos-cart-row-name">${line.name}</div>
                    ${priceSub}
                </div>
                <div class="pos-cart-price">${formatMoney(lineTotal)}</div>
                ${removeCol}
            </div>`;
    }

    function updateLinePrice(productId, rawValue) {
        const line = state.cart.find((item) => item.id === productId);
        if (!line) return;
        const basePrice = line.base_unit_price ?? line.unit_price;
        const parsed = Number(rawValue);
        if (!rawValue || Number.isNaN(parsed)) {
            line.unit_price = basePrice;
            renderCartPanel(true);
            return;
        }
        const normalized = Math.round(parsed * 100) / 100;
        if (normalized < basePrice) {
            showAlert(`ราคาต้องไม่ต่ำกว่าราคาเริ่มต้น ${formatMoney(basePrice)} บาท`);
            line.unit_price = basePrice;
            renderCartPanel(true);
            return;
        }
        if (line.unit_price === normalized) return;
        line.unit_price = normalized;
        renderCartPanel(true);
    }

    function requisitionCartRowHtml(line) {
        return `
            <div class="pos-cart-row pos-cart-row--editable pos-req-cart-row">
                <div class="pos-cart-qty">
                    <div class="pos-qty-stepper">
                        <button type="button" class="pos-step-btn" data-req-action="dec" data-id="${line.id}">−</button>
                        <input
                            type="number"
                            class="pos-qty-input"
                            data-req-qty-id="${line.id}"
                            value="${line.quantity}"
                            min="1"
                            step="1"
                            inputmode="numeric"
                        />
                        <button type="button" class="pos-step-btn" data-req-action="inc" data-id="${line.id}">+</button>
                    </div>
                </div>
                <div class="pos-cart-info">
                    <div class="pos-cart-row-name">${line.name}</div>
                </div>
                <div class="pos-cart-remove">
                    <button type="button" class="pos-remove-btn" data-req-action="remove" data-id="${line.id}" aria-label="ลบ">×</button>
                </div>
            </div>`;
    }

    function parseRequisitionQty(rawValue) {
        const parsed = Number(rawValue);
        if (!rawValue || Number.isNaN(parsed) || parsed <= 0) {
            return 1;
        }
        return Math.round(parsed);
    }

    function syncRequisitionQtyFromInput(productId) {
        const line = state.requisitionCart.find((item) => item.id === productId);
        if (!line) return;
        const input = document.querySelector(`#requisition-cart-list [data-req-qty-id="${productId}"]`);
        if (!input) return;
        line.quantity = parseRequisitionQty(input.value);
    }

    function updateRequisitionQty(productId, rawValue) {
        const line = state.requisitionCart.find((item) => item.id === productId);
        if (!line) return;
        const normalized = parseRequisitionQty(rawValue);
        if (line.quantity === normalized) {
            return;
        }
        line.quantity = normalized;
        renderRequisitionCart();
    }

    function renderCartPanel(editable = true) {
        const bodies = document.querySelectorAll(".js-cart-table-body");
        const totals = computeTotals();

        bodies.forEach((body) => {
            body.innerHTML = "";
            if (!state.cart.length) {
                body.innerHTML = '<div class="pos-empty">เลือกสินค้าเพื่อเพิ่มในตะกร้า</div>';
            } else {
                state.cart.forEach((line) => {
                    body.insertAdjacentHTML("beforeend", cartRowHtml(line, editable && body.id === "cart-list"));
                });
            }
        });

        document.querySelectorAll(".js-summary-subtotal").forEach((el) => {
            el.textContent = formatMoney(totals.subtotal);
        });
        document.querySelectorAll(".js-summary-discount").forEach((el) => {
            el.textContent = formatMoney(totals.discountAmount);
        });
        document.querySelectorAll(".js-summary-total").forEach((el) => {
            el.textContent = formatMoney(totals.total);
        });
        document.querySelectorAll(".js-summary-items").forEach((el) => {
            el.textContent = String(Math.round(totals.itemQty));
        });

        const checkoutBtn = document.getElementById("checkout-btn");
        if (checkoutBtn) checkoutBtn.disabled = !state.cart.length || !state.session;

        updateSessionHeader();
        if (state.paymentMethod === "transfer") {
            state.amountPaidInput = String(totals.total);
            updateTransferAmountDisplay();
        } else {
            updateAmountDisplay();
        }
    }

    function updateSessionHeader() {
        const badge = document.getElementById("pos-session-badge");
        const banner = document.getElementById("no-session-banner");
        if (badge) {
            badge.textContent = state.session ? String(state.session.id) : "ปิดแล้ว";
        }
        if (banner) {
            banner.hidden = !!state.session;
        }
    }

    function requireOpenSession(message) {
        if (state.session) return true;
        showAlert(message || "กรุณาเปิดกะก่อนทำรายการขาย");
        showScreen("openSession");
        return false;
    }

    function renderProducts() {
        const grid = document.getElementById("product-grid");
        if (!grid) return;
        grid.innerHTML = "";
        if (!state.products.length) {
            grid.innerHTML = '<div class="pos-empty">ไม่มีสินค้าในสต็อกร้าน</div>';
            return;
        }
        state.products.forEach((product) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "pos-product";
            if (!product.can_sell) {
                button.classList.add("pos-product-disabled");
            }
            const priceHtml = product.can_sell
                ? `<div class="pos-product-price">${formatMoney(product.sell_price_thb)}</div>`
                : `<div class="pos-product-no-price">ยังไม่ตั้งราคาขาย</div>`;
            button.innerHTML = `
                ${product.image_url ? `<img class="pos-product-image" src="${product.image_url}" alt="">` : `<div class="pos-product-image-empty"></div>`}
                <div class="pos-product-name">${product.name}</div>
                <div class="pos-product-meta">คงเหลือ ${formatQty(product.available_qty)}</div>
                ${priceHtml}
            `;
            button.addEventListener("click", () => {
                if (!product.can_sell) {
                    showAlert("สินค้านี้ยังไม่ได้ตั้งราคาขาย กรุณาตั้ง Sell Price (THB) ที่ Product Variant");
                    return;
                }
                addToCart(product);
            });
            grid.appendChild(button);
        });
    }

    function findProductByBarcode(code) {
        const trimmed = (code || "").trim();
        if (!trimmed) return null;
        return state.products.find(
            (p) => p.barcode === trimmed || (p.sku || "").toLowerCase() === trimmed.toLowerCase()
        );
    }

    function addToCart(product) {
        const existing = state.cart.find((line) => line.id === product.id);
        if (existing) {
            if (existing.quantity >= product.available_qty) return;
            existing.quantity += 1;
        } else {
            state.cart.push({
                id: product.id,
                name: product.name,
                unit_price: product.sell_price_thb,
                base_unit_price: product.sell_price_thb,
                available_qty: product.available_qty,
                quantity: 1,
            });
        }
        renderCartPanel(true);
    }

    function mergeProduct(product) {
        const index = state.products.findIndex((item) => item.id === product.id);
        if (index >= 0) {
            state.products[index] = product;
        } else {
            state.products.push(product);
        }
        renderProducts();
    }

    async function handleBarcodeScanned(code) {
        const trimmed = (code || "").trim();
        if (!trimmed) return;
        let product = findProductByBarcode(trimmed);
        if (!product) {
            try {
                const data = await rpc("/pos/api/products/barcode", {
                    token: state.token,
                    barcode: trimmed,
                });
                product = data.product;
                if (product) mergeProduct(product);
            } catch (error) {
                showAlert(error.message || "ไม่พบสินค้าจากบาร์โค้ดนี้");
                return;
            }
        }
        if (!product) {
            showAlert("ไม่พบสินค้าจากบาร์โค้ดนี้");
            return;
        }
        if (!product.can_sell) {
            showAlert("สินค้านี้ยังไม่ได้ตั้งราคาขาย กรุณาตั้ง Sell Price (THB) ที่ Product Variant");
            return;
        }
        if (product.available_qty <= 0) {
            showAlert("สินค้านี้ไม่มีในสต็อกร้าน");
            return;
        }
        addToCart(product);
    }

    async function addByBarcode() {
        const input = document.getElementById("barcode-input");
        if (!input) return;
        const code = input.value.trim();
        if (!code) return;
        await handleBarcodeScanned(code);
        input.value = "";
        input.focus();
    }

    async function handleRequisitionBarcode(code) {
        const trimmed = (code || "").trim();
        if (!trimmed) return;
        let product = state.requisitionProducts.find(
            (item) =>
                item.barcode === trimmed ||
                (item.sku || "").toLowerCase() === trimmed.toLowerCase()
        );
        if (!product) {
            const data = await rpc("/pos/api/requisition/products", {
                token: state.token,
                search: trimmed,
                page: 1,
                page_size: PAGE_SIZE,
            });
            product = (data.products || []).find(
                (item) =>
                    item.barcode === trimmed ||
                    (item.sku || "").toLowerCase() === trimmed.toLowerCase()
            );
        }
        if (!product) {
            showAlert("ไม่พบสินค้าจากบาร์โค้ดนี้");
            return;
        }
        addToRequisitionCart(product);
    }

    async function openBarcodeScanner(mode = "pos") {
        if (typeof Html5Qrcode === "undefined") {
            showAlert("ไม่สามารถโหลดตัวสแกนบาร์โค้ดได้ กรุณารีเฟรชหน้า");
            return;
        }
        if (mode === "pos" && !requireOpenSession()) return;

        barcodeScannerMode = mode;
        const modal = document.getElementById("barcode-scanner-modal");
        showError("barcode-scanner-error", "");
        modal?.classList.add("show");

        barcodeScanner = new Html5Qrcode("barcode-scanner-region");
        const config = {
            fps: 10,
            qrbox: { width: 280, height: 120 },
        };
        if (window.Html5QrcodeSupportedFormats) {
            config.formatsToSupport = [
                Html5QrcodeSupportedFormats.EAN_13,
                Html5QrcodeSupportedFormats.EAN_8,
                Html5QrcodeSupportedFormats.CODE_128,
                Html5QrcodeSupportedFormats.CODE_39,
                Html5QrcodeSupportedFormats.UPC_A,
                Html5QrcodeSupportedFormats.UPC_E,
                Html5QrcodeSupportedFormats.QR_CODE,
            ];
        }

        try {
            await barcodeScanner.start(
                { facingMode: "environment" },
                config,
                (decodedText) => {
                    closeBarcodeScanner();
                    if (barcodeScannerMode === "requisition") {
                        handleRequisitionBarcode(decodedText).catch((error) => {
                            showAlert(error.message || "ไม่สามารถค้นหาสินค้าได้");
                        });
                    } else {
                        handleBarcodeScanned(decodedText);
                    }
                },
                () => {}
            );
            barcodeScannerActive = true;
        } catch (error) {
            showError("barcode-scanner-error", `ไม่สามารถเปิดกล้องได้: ${error.message || error}`);
        }
    }

    async function closeBarcodeScanner() {
        const modal = document.getElementById("barcode-scanner-modal");
        modal?.classList.remove("show");
        if (barcodeScanner && barcodeScannerActive) {
            try {
                await barcodeScanner.stop();
            } catch (_) {
                /* ignore */
            }
            try {
                await barcodeScanner.clear();
            } catch (_) {
                /* ignore */
            }
            barcodeScannerActive = false;
        }
        barcodeScanner = null;
    }

    function updateCart(action, productId) {
        const line = state.cart.find((item) => item.id === productId);
        if (!line) return;
        if (action === "inc") {
            if (line.quantity >= line.available_qty) return;
            line.quantity += 1;
        } else if (action === "dec") {
            line.quantity -= 1;
            if (line.quantity <= 0) {
                state.cart = state.cart.filter((item) => item.id !== productId);
            }
        } else if (action === "remove") {
            state.cart = state.cart.filter((item) => item.id !== productId);
        }
        renderCartPanel(true);
    }

    function updateAmountDisplay() {
        const display = document.getElementById("amount-paid-display");
        if (!display) return;
        const raw = state.amountPaidInput;
        if (!raw) {
            display.textContent = "0";
            return;
        }
        if (raw.includes(".")) {
            display.textContent = raw;
        } else {
            display.textContent = Number(raw).toLocaleString("th-TH");
        }
    }

    function numpadPress(key) {
        if (key === "clear") {
            state.amountPaidInput = "";
        } else if (key === ".") {
            if (!state.amountPaidInput.includes(".")) {
                state.amountPaidInput = state.amountPaidInput ? `${state.amountPaidInput}.` : "0.";
            }
        } else {
            if (state.amountPaidInput === "0") {
                state.amountPaidInput = key;
            } else {
                const next = state.amountPaidInput + key;
                if (next.includes(".")) {
                    const [, dec] = next.split(".");
                    if (dec && dec.length > 2) return;
                }
                state.amountPaidInput = next;
            }
        }
        updateAmountDisplay();
    }

    function updateTransferAmountDisplay() {
        const display = document.getElementById("transfer-amount-display");
        if (!display) return;
        display.textContent = formatMoney(computeTotals().total);
    }

    function clearTransferSlip() {
        state.transferSlip = null;
        const preview = document.getElementById("transfer-slip-preview");
        const image = document.getElementById("transfer-slip-image");
        const input = document.getElementById("transfer-slip-input");
        const btn = document.getElementById("transfer-slip-btn");
        if (preview) preview.hidden = true;
        if (image) image.removeAttribute("src");
        if (input) input.value = "";
        if (btn) btn.hidden = true;
    }

    function openTransferSlipCapture(pendingPay = false) {
        pendingPayAfterSlip = pendingPay;
        document.getElementById("transfer-slip-input")?.click();
    }

    function renderTransferSlipPreview() {
        const preview = document.getElementById("transfer-slip-preview");
        const image = document.getElementById("transfer-slip-image");
        const btn = document.getElementById("transfer-slip-btn");
        if (!preview || !image || !state.transferSlip) return;
        image.src = state.transferSlip.previewUrl;
        preview.hidden = false;
        if (btn) btn.hidden = true;
    }

    function handleTransferSlipFile(file) {
        if (!file) return;
        if (!file.type.startsWith("image/")) {
            showError("checkout-error", "กรุณาเลือกไฟล์รูปภาพ");
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            const result = reader.result;
            const base64 = String(result).split(",")[1];
            state.transferSlip = {
                base64,
                filename: file.name || "transfer-slip.jpg",
                previewUrl: result,
            };
            renderTransferSlipPreview();
            showError("checkout-error", "");
            if (pendingPayAfterSlip) {
                pendingPayAfterSlip = false;
                showPayConfirmModal();
            }
        };
        reader.readAsDataURL(file);
    }

    function setPaymentMethod(method) {
        state.paymentMethod = method;
        document.querySelectorAll(".pos-pay-tab").forEach((tab) => {
            tab.classList.toggle("active", tab.dataset.payTab === method);
        });
        const cashPanel = document.getElementById("cash-payment-panel");
        const transferPanel = document.getElementById("transfer-payment-panel");
        if (cashPanel) cashPanel.hidden = method !== "cash";
        if (transferPanel) transferPanel.hidden = method !== "transfer";
        if (method === "transfer") {
            const totals = computeTotals();
            state.amountPaidInput = String(totals.total);
            updateTransferAmountDisplay();
        } else {
            pendingPayAfterSlip = false;
            clearTransferSlip();
            showError("checkout-error", "");
            updateAmountDisplay();
        }
    }

    function openPaymentScreen() {
        state.amountPaidInput = "";
        state.paymentMethod = "cash";
        state.transferSlip = null;
        pendingPayAfterSlip = false;
        showError("checkout-error", "");
        clearTransferSlip();
        setPaymentMethod("cash");
        renderCartPanel(false);
        updateAmountDisplay();
        showScreen("payment");
    }

    function openDiscountScreen() {
        if (!requireOpenSession()) return;
        const discountType = document.getElementById("discount-type");
        const discountValue = document.getElementById("discount-value");
        const orderNote = document.getElementById("order-note");
        if (discountType) discountType.value = state.discountType;
        if (discountValue) discountValue.value = state.discountValue || "";
        if (orderNote) orderNote.value = state.orderNote || "";
        renderCartPanel(false);
        showScreen("discount");
    }

    function showPayConfirmModal() {
        if (!requireOpenSession()) return;
        const totals = computeTotals();
        if (state.paymentMethod === "transfer") {
            if (!state.transferSlip?.base64) {
                openTransferSlipCapture(true);
                return;
            }
            state.amountPaidInput = String(totals.total);
        } else if (totals.amountPaid < totals.total) {
            showError("checkout-error", "จำนวนเงินที่รับต้องไม่น้อยกว่ายอดชำระ");
            return;
        }
        showError("checkout-error", "");
        document.getElementById("modal-total").textContent = formatMoney(totals.total);
        document.getElementById("modal-paid").textContent = formatMoney(
            state.paymentMethod === "transfer" ? totals.total : totals.amountPaid
        );
        document.getElementById("modal-change").textContent = formatMoney(
            state.paymentMethod === "transfer" ? 0 : totals.changeAmount
        );
        document.getElementById("pay-confirm-modal").classList.add("show");
    }

    function hidePayConfirmModal() {
        document.getElementById("pay-confirm-modal").classList.remove("show");
    }

    async function loadProducts() {
        const data = await rpc("/pos/api/products", {
            token: state.token,
            search: state.search,
            page: listState.products.page,
            page_size: PAGE_SIZE,
        });
        state.products = data.products || [];
        applyPaginationMeta("products", data);
        renderProducts();
        renderPaginationBar("products", "products-pagination");
    }

    const debouncedLoadProducts = debounce(async () => {
        try {
            await loadProducts();
        } catch (error) {
            console.error("loadProducts failed:", error);
        }
    }, 300);

    function renderRequisitionProducts() {
        const list = document.getElementById("requisition-product-list");
        if (!list) return;
        list.innerHTML = "";
        if (!state.requisitionProducts.length) {
            list.innerHTML = '<div class="pos-empty">ไม่พบสินค้า</div>';
            return;
        }
        state.requisitionProducts.forEach((product) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "pos-row-item";
            const metaParts = [];
            if (product.sku) metaParts.push(`SKU ${product.sku}`);
            if (product.barcode) metaParts.push(`บาร์โค้ด ${product.barcode}`);
            const meta = metaParts.length ? metaParts.join(" · ") : "แตะเพื่อเพิ่ม";
            const priceLabel =
                product.has_sell_price && product.sell_price_thb > 0
                    ? formatMoney(product.sell_price_thb)
                    : "—";
            button.innerHTML = `
                <div class="pos-row-main">
                    <div class="pos-row-title">${product.name}</div>
                    <div class="pos-row-meta">${meta}</div>
                </div>
                <div class="pos-row-price">${priceLabel}</div>
            `;
            button.addEventListener("click", () => addToRequisitionCart(product));
            list.appendChild(button);
        });
    }

    function renderRequisitionCart() {
        const list = document.getElementById("requisition-cart-list");
        const submitBtn = document.getElementById("submit-requisition-btn");
        if (!list || !submitBtn) return;
        list.innerHTML = "";
        if (!state.requisitionCart.length) {
            list.innerHTML = '<div class="pos-empty">ยังไม่มีรายการเบิก</div>';
        } else {
            state.requisitionCart.forEach((line) => {
                list.insertAdjacentHTML("beforeend", requisitionCartRowHtml(line));
            });
        }
        submitBtn.disabled = !state.requisitionCart.length;
    }

    function addToRequisitionCart(product) {
        const existing = state.requisitionCart.find((line) => line.id === product.id);
        if (existing) {
            existing.quantity += 1;
        } else {
            state.requisitionCart.push({ id: product.id, name: product.name, quantity: 1 });
        }
        renderRequisitionCart();
    }

    function updateRequisitionCart(action, productId) {
        const line = state.requisitionCart.find((item) => item.id === productId);
        if (!line) return;
        if (action === "inc" || action === "dec") {
            syncRequisitionQtyFromInput(productId);
        }
        if (action === "inc") {
            line.quantity += 1;
        } else if (action === "dec") {
            line.quantity -= 1;
            if (line.quantity <= 0) {
                state.requisitionCart = state.requisitionCart.filter((item) => item.id !== productId);
            }
        } else if (action === "remove") {
            state.requisitionCart = state.requisitionCart.filter((item) => item.id !== productId);
        }
        renderRequisitionCart();
    }

    async function loadRequisitionProducts() {
        const data = await rpc("/pos/api/requisition/products", {
            token: state.token,
            search: state.requisitionSearch,
            page: listState.requisitionProducts.page,
            page_size: PAGE_SIZE,
        });
        state.requisitionProducts = data.products || [];
        applyPaginationMeta("requisitionProducts", data);
        renderRequisitionProducts();
        renderPaginationBar("requisitionProducts", "requisition-products-pagination");
    }

    async function submitRequisition() {
        showError("requisition-error", "");
        const success = document.getElementById("requisition-success");
        if (success) {
            success.hidden = true;
            success.textContent = "";
        }
        state.requisitionCart.forEach((line) => syncRequisitionQtyFromInput(line.id));
        const lines = state.requisitionCart.map((line) => ({
            product_variant_id: line.id,
            quantity: line.quantity,
        }));
        const note = document.getElementById("requisition-note")?.value || "";
        const result = await rpc("/pos/api/requisition/create", {
            token: state.token,
            lines,
            note,
        });
        state.requisitionCart = [];
        if (document.getElementById("requisition-note")) {
            document.getElementById("requisition-note").value = "";
        }
        renderRequisitionCart();
        state.selectedRequisition = result.requisition;
        renderRequisitionDetail();
        showScreen("requisitionDetail");
    }

    function renderRequisitionAllocationHtml(allocations) {
        if (!allocations?.length) {
            return '<div class="pos-detail-wh-pending">รอจัดสรรคลัง</div>';
        }
        return allocations
            .map(
                (alloc) => `
                <div class="pos-detail-allocation">
                    <span class="pos-detail-wh-tag">${alloc.warehouse_name || "—"}</span>
                    <span>${formatQty(alloc.quantity)}</span>
                </div>`
            )
            .join("");
    }

    function renderRequisitionList() {
        const container = document.getElementById("requisition-list-container");
        if (!container) return;
        if (!state.requisitions.length) {
            container.classList.add("pos-order-list--empty");
            container.innerHTML = '<div class="pos-empty">ยังไม่มีประวัติการเบิก</div>';
            return;
        }
        container.classList.remove("pos-order-list--empty");
        container.innerHTML = state.requisitions
            .map((row) => {
                const linesPreview = row.items_preview || (row.line_count ? `${row.line_count} รายการ` : "");
                const warehouse = row.warehouse_name ? `คลัง: ${row.warehouse_name}` : "";
                return `
                <button type="button" class="pos-row-item pos-row-item-block pos-requisition-card" data-requisition-id="${row.id}">
                    <div class="pos-requisition-card-top">
                        <div class="pos-row-main">
                            <div class="pos-row-title">${row.number}</div>
                            <div class="pos-row-meta">${formatDateTime(row.requested_at)}</div>
                        </div>
                        <div class="pos-requisition-card-side">
                            <span class="pos-badge ${requisitionBadgeClass(row.state)}">${stateLabels[row.state] || row.state}</span>
                            <svg class="pos-row-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
                        </div>
                    </div>
                    ${linesPreview ? `<div class="pos-row-extra">${linesPreview}</div>` : ""}
                    ${warehouse ? `<div class="pos-row-extra">${warehouse}</div>` : ""}
                    <div class="pos-row-hint">แตะเพื่อดูรายละเอียด</div>
                </button>`;
            })
            .join("");
    }

    function renderRequisitionDetail() {
        const container = document.getElementById("requisition-detail-container");
        const req = state.selectedRequisition;
        if (!container || !req) return;

        const timeline = [
            ["ส่งคำขอ", req.requested_at],
            ["จัดเตรียม", req.prepared_at],
            ["รับสินค้า", req.received_at],
            ["เสร็จสิ้น", req.done_at],
        ]
            .filter(([, value]) => value)
            .map(([label, value]) => `<div class="pos-detail-row"><span>${label}</span><span>${formatDateTime(value)}</span></div>`)
            .join("");

        const linesHtml = (req.lines || [])
            .map(
                (line) => `
                <div class="pos-detail-line">
                    <div class="pos-detail-line-head">
                        <div class="pos-detail-line-name">${line.product_name}</div>
                        <div class="pos-detail-line-qty">ขอ ${formatQty(line.requested_qty)}</div>
                    </div>
                    <div class="pos-detail-line-allocations">
                        ${renderRequisitionAllocationHtml(line.allocations)}
                    </div>
                </div>`
            )
            .join("");

        const warehouseBlock = req.warehouse_names?.length
            ? req.warehouse_names.map((name) => `<span class="pos-detail-wh-tag">${name}</span>`).join("")
            : req.warehouse_name
              ? `<span class="pos-detail-wh-tag">${req.warehouse_name}</span>`
              : "";

        container.innerHTML = `
            <div class="pos-detail-card">
                <div class="pos-detail-head">
                    <div>
                        <div class="pos-detail-number">${req.number}</div>
                        <div class="pos-row-meta">${formatDateTime(req.requested_at)}</div>
                    </div>
                    <span class="pos-badge ${requisitionBadgeClass(req.state)}">${stateLabels[req.state] || req.state}</span>
                </div>
                ${
                    warehouseBlock
                        ? `<div class="pos-detail-section"><div class="pos-detail-section-title">คลังต้นทาง</div><div class="pos-detail-wh-tags">${warehouseBlock}</div></div>`
                        : ""
                }
                ${req.note ? `<div class="pos-detail-note">${req.note}</div>` : ""}
                ${timeline ? `<div class="pos-detail-section"><div class="pos-detail-section-title">สถานะ</div>${timeline}</div>` : ""}
                <div class="pos-detail-section">
                    <div class="pos-detail-section-title">รายการสินค้า / คลังที่เบิก</div>
                    ${linesHtml || '<div class="pos-empty">ไม่มีรายการ</div>'}
                </div>
                ${
                    req.can_mark_received
                        ? `<button type="button" id="requisition-mark-received-btn" class="pos-primary-btn pos-btn-block" style="margin-top:12px;">รับสินค้าแล้ว</button>`
                        : ""
                }
            </div>`;

        const receivedBtn = document.getElementById("requisition-mark-received-btn");
        if (receivedBtn) {
            receivedBtn.addEventListener("click", async () => {
                try {
                    showError("requisition-detail-error", "");
                    await rpc("/pos/api/requisition/received", {
                        token: state.token,
                        requisition_id: req.id,
                    });
                    await openRequisitionDetail(req.id);
                } catch (error) {
                    showError("requisition-detail-error", error.message);
                }
            });
        }
    }

    async function loadRequisitionList() {
        const range = getDateFilterRange("requisitions");
        const data = await rpc("/pos/api/requisition/list", {
            token: state.token,
            page: listState.requisitions.page,
            page_size: PAGE_SIZE,
            date_from: range.from,
            date_to: range.to,
        });
        state.requisitions = data.requisitions || [];
        applyPaginationMeta("requisitions", data);
        renderRequisitionList();
        renderPaginationBar("requisitions", "requisition-list-pagination");
    }

    async function openRequisitionDetail(requisitionId) {
        showError("requisition-detail-error", "");
        const data = await rpc("/pos/api/requisition/detail", {
            token: state.token,
            requisition_id: requisitionId,
        });
        state.selectedRequisition = data.requisition;
        renderRequisitionDetail();
        showScreen("requisitionDetail");
    }

    async function openRequisitionHistoryScreen() {
        showError("requisition-list-error", "");
        listState.requisitions.page = 1;
        dateFilters.requisitions.date = todayDateInputValue();
        const dateEl = document.getElementById("requisition-date");
        if (dateEl) dateEl.value = dateFilters.requisitions.date;
        await loadRequisitionList();
        showScreen("requisitionList");
    }

    async function openRequisitionScreen() {
        state.requisitionCart = [];
        state.requisitionSearch = "";
        listState.requisitionProducts.page = 1;
        if (document.getElementById("requisition-search")) {
            document.getElementById("requisition-search").value = "";
        }
        showError("requisition-error", "");
        const success = document.getElementById("requisition-success");
        if (success) {
            success.hidden = true;
        }
        await loadRequisitionProducts();
        renderRequisitionCart();
        showScreen("requisition");
    }

    function updateDrawerInfo() {
        const storeEl = document.getElementById("drawer-store-name");
        const userEl = document.getElementById("drawer-user-name");
        if (storeEl && state.user) storeEl.textContent = state.user.store_name || "ร้านค้า";
        if (userEl && state.user) userEl.textContent = state.user.name || "พนักงาน";
    }

    function openDrawer() {
        updateDrawerInfo();
        const backdrop = document.getElementById("pos-drawer-backdrop");
        if (!backdrop) return;
        backdrop.classList.add("show");
        document.body.classList.add("pos-drawer-open");
    }

    function closeDrawer() {
        const backdrop = document.getElementById("pos-drawer-backdrop");
        if (backdrop) backdrop.classList.remove("show");
        document.body.classList.remove("pos-drawer-open");
    }

    async function handleMenuAction(action) {
        closeDrawer();
        if (action === "pos") {
            if (state.session) {
                showScreen("pos");
            } else {
                showScreen("openSession");
            }
            return;
        }
        if (action === "close-session") {
            if (!state.session) {
                showAlert("ยังไม่มีกะที่เปิดอยู่");
                showScreen("openSession");
                return;
            }
            document.getElementById("closing-cash").value = "";
            showError("close-session-error", "");
            showScreen("closeSession");
            return;
        }
        if (action === "requisition") {
            await openRequisitionScreen();
            return;
        }
        if (action === "requisition-history") {
            await openRequisitionHistoryScreen();
            return;
        }
        if (action === "stock") {
            await openStockScreen();
            return;
        }
        if (action === "sales") {
            await openSalesHistoryScreen();
        }
    }

    async function loadStock() {
        const data = await rpc("/pos/api/stock", {
            token: state.token,
            search: state.stockSearch,
            page: listState.stock.page,
            page_size: PAGE_SIZE,
        });
        state.stockSummary = data.summary || [];
        renderStock();
        renderPaginationBar("stock", "stock-pagination");
    }

    function renderStock() {
        const container = document.getElementById("stock-list-container");
        if (!container) return;

        const rows = state.stockSummary;

        if (!rows.length) {
            container.innerHTML = '<div class="pos-empty">ไม่มีสต็อกในร้าน</div>';
            return;
        }
        container.innerHTML = rows
            .map(
                (row) => `
            <div class="pos-row-item pos-row-static">
                <div class="pos-row-main">
                    <div class="pos-row-title">${row.product_name}</div>
                    <div class="pos-row-meta">ราคาขาย ${formatMoney(row.sell_price_thb)} บาท/ชิ้น</div>
                </div>
                <div class="pos-row-price">${formatQty(row.total_qty)} ชิ้น</div>
            </div>`
            )
            .join("");
    }

    async function openStockScreen() {
        state.stockSearch = "";
        listState.stock.page = 1;
        const search = document.getElementById("stock-search");
        if (search) search.value = "";
        await loadStock();
        showScreen("stock");
    }

    async function loadSalesHistory() {
        const range = getDateFilterRange("sales");
        const data = await rpc("/pos/api/orders/list", {
            token: state.token,
            page: listState.sales.page,
            page_size: PAGE_SIZE,
            date_from: range.from,
            date_to: range.to,
        });
        state.salesOrders = data.orders || [];
        applyPaginationMeta("sales", data);
        renderSalesHistory();
        renderPaginationBar("sales", "sales-pagination");
    }

    function renderSalesHistory() {
        const container = document.getElementById("sales-history-container");
        if (!container) return;
        if (!state.salesOrders.length) {
            container.classList.add("pos-order-list--empty");
            container.innerHTML = '<div class="pos-empty">ยังไม่มีประวัติการขาย</div>';
            return;
        }
        container.classList.remove("pos-order-list--empty");
        container.innerHTML = state.salesOrders
            .map((order) => {
                const badgeClass = order.state === "cancelled" ? "pos-badge-cancelled" : "pos-badge-done";
                const linesPreview = (order.lines || [])
                    .slice(0, 3)
                    .map((line) => `${line.product_name} × ${formatQty(line.quantity)}`)
                    .join(" · ");
                const moreLines =
                    (order.lines || []).length > 3 ? ` · +${order.lines.length - 3} รายการ` : "";
                const cancelHint =
                    order.state === "cancelled"
                        ? `<div class="pos-row-extra">${
                              order.return_stock ? "คืนสต็อกแล้ว" : "ไม่คืนสต็อก"
                          }${order.cancel_reason ? ` · ${order.cancel_reason}` : ""}</div>`
                        : "";
                return `
                <button type="button" class="pos-row-item pos-row-item-block pos-history-card" data-order-id="${order.id}">
                    <div class="pos-history-card-top">
                        <div class="pos-row-main">
                            <div class="pos-row-title">${order.number}</div>
                            <div class="pos-row-meta">${formatDateTime(order.order_date)}</div>
                        </div>
                        <div class="pos-history-card-side">
                            <span class="pos-badge ${badgeClass}">${orderStateLabels[order.state] || order.state}</span>
                            <div class="pos-row-price">${formatMoney(order.total)} บาท</div>
                            <svg class="pos-row-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
                        </div>
                    </div>
                    ${linesPreview ? `<div class="pos-row-extra">${linesPreview}${moreLines}</div>` : ""}
                    ${cancelHint}
                    <div class="pos-row-hint">แตะเพื่อดูรายละเอียด</div>
                </button>`;
            })
            .join("");
    }

    function salesOrderBadgeClass(orderState) {
        return orderState === "cancelled" ? "pos-badge-cancelled" : "pos-badge-done";
    }

    function renderSalesOrderDetail() {
        const container = document.getElementById("sales-detail-container");
        const order = state.selectedSalesOrder;
        if (!container || !order) return;

        const linesHtml = (order.lines || [])
            .map(
                (line) => `
                <div class="pos-detail-line">
                    <div class="pos-detail-line-head">
                        <div class="pos-detail-line-name">${line.product_name}</div>
                        <div class="pos-detail-line-qty">${formatQty(line.quantity)} × ${formatMoney(line.unit_price)}</div>
                    </div>
                    <div class="pos-detail-line-meta">${formatMoney(line.subtotal)} บาท</div>
                </div>`
            )
            .join("");

        const paymentRows = [
            ["ชำระโดย", paymentMethodLabels[order.payment_method] || "เงินสด"],
            ["รวม", formatMoney(order.subtotal)],
            ["ส่วนลด", formatMoney(order.discount_amount)],
            ["ยอดชำระ", formatMoney(order.total)],
            ["รับเงิน", formatMoney(order.amount_paid)],
            ["เงินทอน", formatMoney(order.change_amount)],
        ]
            .map(
                ([label, value]) =>
                    `<div class="pos-detail-row${label === "ยอดชำระ" ? " pos-detail-row--strong" : ""}"><span>${label}</span><span>${label === "ชำระโดย" ? value : `${value} บาท`}</span></div>`
            )
            .join("");

        const cancelBlock =
            order.state === "cancelled"
                ? `<div class="pos-detail-section">
                    <div class="pos-detail-section-title">การยกเลิก</div>
                    <div class="pos-detail-row"><span>ยกเลิกเมื่อ</span><span>${formatDateTime(order.cancelled_at)}</span></div>
                    <div class="pos-detail-row"><span>คืนสต็อก</span><span>${order.return_stock ? "คืนแล้ว" : "ไม่คืน"}</span></div>
                    ${
                        order.cancel_reason
                            ? `<div class="pos-detail-note">${order.cancel_reason}</div>`
                            : ""
                    }
                </div>`
                : "";

        container.innerHTML = `
            <div class="pos-detail-card">
                <div class="pos-detail-head">
                    <div>
                        <div class="pos-detail-number">${order.number}</div>
                        <div class="pos-row-meta">${formatDateTime(order.order_date)}</div>
                        <div class="pos-row-meta">พนักงาน: ${order.cashier_name || "-"}</div>
                    </div>
                    <span class="pos-badge ${salesOrderBadgeClass(order.state)}">${orderStateLabels[order.state] || order.state}</span>
                </div>
                <div class="pos-detail-section">
                    <div class="pos-detail-section-title">รายการสินค้า</div>
                    ${linesHtml || '<div class="pos-empty">ไม่มีรายการ</div>'}
                </div>
                <div class="pos-detail-section">
                    <div class="pos-detail-section-title">สรุปยอด</div>
                    ${paymentRows}
                </div>
                ${cancelBlock}
                <div class="pos-detail-actions">
                    <button type="button" id="sales-detail-print-btn" class="pos-primary-btn pos-btn-block">พิมพ์ใบเสร็จ</button>
                    ${
                        order.can_cancel
                            ? `<button type="button" id="sales-detail-cancel-btn" class="pos-btn pos-btn-danger pos-btn-block">ยกเลิกรายการ</button>`
                            : ""
                    }
                </div>
            </div>`;

        document.getElementById("sales-detail-print-btn")?.addEventListener("click", () => {
            printReceipt(order);
        });
        document.getElementById("sales-detail-cancel-btn")?.addEventListener("click", () => {
            openCancelOrderModal(order);
        });
    }

    async function openSalesOrderDetail(orderId) {
        showError("sales-detail-error", "");
        const data = await rpc("/pos/api/orders/detail", {
            token: state.token,
            order_id: orderId,
        });
        state.selectedSalesOrder = data.order;
        renderSalesOrderDetail();
        showScreen("salesDetail");
    }

    async function openSalesHistoryScreen() {
        showError("sales-history-error", "");
        listState.sales.page = 1;
        dateFilters.sales.date = todayDateInputValue();
        const dateEl = document.getElementById("sales-date");
        if (dateEl) dateEl.value = dateFilters.sales.date;
        await loadSalesHistory();
        showScreen("salesHistory");
    }

    function openCancelOrderModal(order) {
        state.cancelOrderId = order.id;
        document.getElementById("cancel-order-number").textContent = order.number;
        document.getElementById("cancel-order-total").textContent = formatMoney(order.total);
        const returnStock = document.getElementById("cancel-return-stock");
        const reasonWrap = document.getElementById("cancel-reason-wrap");
        const reason = document.getElementById("cancel-reason");
        if (returnStock) returnStock.checked = true;
        if (reason) reason.value = "";
        if (reasonWrap) reasonWrap.style.display = "none";
        showError("cancel-order-error", "");
        document.getElementById("cancel-order-modal").classList.add("show");
    }

    function closeCancelOrderModal() {
        state.cancelOrderId = null;
        document.getElementById("cancel-order-modal").classList.remove("show");
    }

    function toggleCancelReasonField() {
        const returnStock = document.getElementById("cancel-return-stock");
        const reasonWrap = document.getElementById("cancel-reason-wrap");
        if (!returnStock || !reasonWrap) return;
        reasonWrap.style.display = returnStock.checked ? "none" : "block";
    }

    async function submitCancelOrder() {
        showError("cancel-order-error", "");
        const returnStock = document.getElementById("cancel-return-stock").checked;
        const cancelReason = document.getElementById("cancel-reason").value.trim();
        if (!returnStock && !cancelReason) {
            showError("cancel-order-error", "กรุณาระบุเหตุผลเมื่อไม่คืนสินค้าเข้าสต็อก");
            return;
        }
        await rpc("/pos/api/orders/cancel", {
            token: state.token,
            order_id: state.cancelOrderId,
            return_stock: returnStock,
            cancel_reason: cancelReason,
        });
        const cancelledOrderId = state.cancelOrderId;
        closeCancelOrderModal();
        await loadSalesHistory();
        if (state.selectedSalesOrder?.id === cancelledOrderId) {
            await openSalesOrderDetail(cancelledOrderId);
        }
        await loadProducts();
    }

    async function bootstrapAfterLogin(data) {
        state.token = data.token;
        state.user = data.user;
        saveAuth();
        if (data.open_session_id) {
            state.session = {
                id: data.open_session_id,
                opening_cash: data.open_session_opening_cash,
            };
            await enterPos();
        } else {
            showScreen("openSession");
        }
    }

    async function enterPos(options = {}) {
        if (!options.skipSessionFetch) {
            const sessionData = await rpc("/pos/api/session/current", { token: state.token });
            state.session = sessionData.session;
            saveAuth();
        }
        if (!state.session) {
            showScreen("openSession");
            return;
        }
        document.getElementById("pos-store-name").textContent = state.user.store_name;
        document.getElementById("pos-user-name").textContent = state.user.name;
        updateSessionHeader();
        try {
            await loadProducts();
        } catch (error) {
            console.error("loadProducts failed:", error);
            state.products = [];
            renderProducts();
        }
        renderCartPanel(true);
        showScreen("pos");
    }

    async function submitOrder() {
        showError("checkout-error", "");
        const totals = computeTotals();
        if (state.paymentMethod === "transfer") {
            if (!state.transferSlip?.base64) {
                showError("checkout-error", "กรุณาแนบสลิปโอนเงิน");
                return;
            }
        } else if (totals.amountPaid < totals.total) {
            showError("checkout-error", "จำนวนเงินที่รับต้องไม่น้อยกว่ายอดชำระ");
            return;
        }
        const lines = state.cart.map((line) => ({
            product_variant_id: line.id,
            quantity: line.quantity,
            unit_price: line.unit_price,
        }));
        const payload = {
            token: state.token,
            lines,
            discount_type: state.discountValue > 0 ? state.discountType : null,
            discount_value: state.discountValue,
            amount_paid: state.paymentMethod === "transfer" ? totals.total : totals.amountPaid,
            payment_method: state.paymentMethod,
        };
        if (state.paymentMethod === "transfer") {
            payload.transfer_slip = state.transferSlip.base64;
            payload.transfer_slip_filename = state.transferSlip.filename;
        }
        const result = await rpc("/pos/api/order/create", payload);
        state.lastOrder = result.order;
        state.lastReceipt = {
            ...result.order,
            note: state.orderNote || "",
        };
        document.getElementById("success-order-number").textContent = result.order.number;
        document.getElementById("success-subtotal").textContent = formatMoney(result.order.subtotal);
        document.getElementById("success-discount").textContent = formatMoney(result.order.discount_amount);
        document.getElementById("success-total").textContent = formatMoney(result.order.total);
        document.getElementById("success-paid").textContent = formatMoney(result.order.amount_paid);
        document.getElementById("success-change").textContent = formatMoney(result.order.change_amount);
        const successChangeCard = document.querySelector(".pos-success-card h2");
        const successChangeNote = document.querySelector(".pos-success-card small");
        if (successChangeCard) {
            successChangeCard.textContent = result.order.payment_method === "transfer" ? "ชำระโดยโอน" : "เงินทอน";
        }
        if (successChangeNote) {
            successChangeNote.textContent = result.order.payment_method === "transfer" ? paymentMethodLabels.transfer : "บาท";
        }
        state.cart = [];
        state.discountValue = 0;
        state.discountType = "percent";
        state.amountPaidInput = "";
        state.paymentMethod = "cash";
        state.transferSlip = null;
        clearTransferSlip();
        state.orderNote = "";
        hidePayConfirmModal();
        await loadProducts();
        showScreen("success");
        printReceipt(state.lastReceipt);
    }

    function bindEvents() {
        const on = (id, event, handler) => {
            const element = document.getElementById(id);
            if (!element) {
                console.warn(`POS: element #${id} not found`);
                return null;
            }
            element.addEventListener(event, handler);
            return element;
        };

        on("pos-alert-ok-btn", "click", hideAlertModal);
        document.getElementById("pos-alert-modal")?.addEventListener("click", (event) => {
            if (event.target.id === "pos-alert-modal") hideAlertModal();
        });

        document.addEventListener("click", (event) => {
            if (event.target.closest(".pos-menu-btn")) {
                event.preventDefault();
                openDrawer();
            }
        });

        on("login-form", "submit", async (event) => {
            event.preventDefault();
            showError("login-error", "");
            try {
                const username = document.getElementById("login-username").value.trim();
                const password = document.getElementById("login-password").value;
                const data = await rpc("/pos/api/login", { username, password });
                await bootstrapAfterLogin(data);
            } catch (error) {
                showError("login-error", error.message);
            }
        });

        on("open-session-form", "submit", async (event) => {
            event.preventDefault();
            showError("open-session-error", "");
            try {
                const openingCash = Number(document.getElementById("opening-cash").value || 0);
                const data = await rpc("/pos/api/session/open", {
                    token: state.token,
                    opening_cash: openingCash,
                });
                state.session = { id: data.session_id, opening_cash: data.opening_cash };
                saveAuth();
                await enterPos();
            } catch (error) {
                showError("open-session-error", error.message);
            }
        });

        document.getElementById("product-search").addEventListener("input", (event) => {
            state.search = event.target.value.trim();
            listState.products.page = 1;
            debouncedLoadProducts();
        });

        document.getElementById("cart-list").addEventListener("click", (event) => {
            const button = event.target.closest("[data-action]");
            if (!button) return;
            updateCart(button.dataset.action, Number(button.dataset.id));
        });
        document.getElementById("cart-list").addEventListener("blur", (event) => {
            const input = event.target.closest("[data-price-id]");
            if (!input) return;
            updateLinePrice(Number(input.dataset.priceId), input.value);
        }, true);
        document.getElementById("cart-list").addEventListener("keydown", (event) => {
            const input = event.target.closest("[data-price-id]");
            if (!input || event.key !== "Enter") return;
            event.preventDefault();
            updateLinePrice(Number(input.dataset.priceId), input.value);
            input.blur();
        });

        document.getElementById("barcode-add-btn").addEventListener("click", () => {
            addByBarcode();
        });
        document.getElementById("barcode-input").addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                addByBarcode();
            }
        });
        document.getElementById("barcode-scan-btn")?.addEventListener("click", () => {
            openBarcodeScanner("pos");
        });
        document.getElementById("barcode-scanner-close-btn")?.addEventListener("click", () => {
            closeBarcodeScanner();
        });
        document.getElementById("barcode-scanner-modal")?.addEventListener("click", (event) => {
            if (event.target.id === "barcode-scanner-modal") {
                closeBarcodeScanner();
            }
        });

        document.getElementById("checkout-btn").addEventListener("click", openDiscountScreen);

        document.getElementById("to-payment-btn").addEventListener("click", openPaymentScreen);

        document.getElementById("clear-discount-btn").addEventListener("click", () => {
            state.discountValue = 0;
            state.discountType = "percent";
            document.getElementById("discount-value").value = "0";
            document.getElementById("discount-type").value = "percent";
            renderCartPanel(false);
        });

        document.getElementById("discount-type").addEventListener("change", (event) => {
            state.discountType = event.target.value;
            renderCartPanel(false);
        });
        document.getElementById("discount-value").addEventListener("input", (event) => {
            state.discountValue = Number(event.target.value || 0);
            renderCartPanel(false);
        });
        document.getElementById("order-note").addEventListener("input", (event) => {
            state.orderNote = event.target.value;
        });

        document.getElementById("numpad").addEventListener("click", (event) => {
            const button = event.target.closest("[data-key]");
            if (!button) return;
            numpadPress(button.dataset.key);
        });

        document.querySelectorAll(".pos-pay-tab").forEach((tab) => {
            tab.addEventListener("click", () => {
                if (tab.disabled) return;
                setPaymentMethod(tab.dataset.payTab);
                showError("checkout-error", "");
            });
        });

        on("transfer-slip-input", "change", (event) => {
            const file = event.target.files?.[0];
            if (!file) {
                pendingPayAfterSlip = false;
                return;
            }
            handleTransferSlipFile(file);
        });
        on("transfer-slip-remove-btn", "click", () => {
            clearTransferSlip();
        });

        document.getElementById("pay-btn").addEventListener("click", showPayConfirmModal);
        document.getElementById("modal-cancel-btn").addEventListener("click", hidePayConfirmModal);
        document.getElementById("modal-confirm-btn").addEventListener("click", async () => {
            try {
                await submitOrder();
            } catch (error) {
                hidePayConfirmModal();
                showError("checkout-error", error.message);
            }
        });

        on("new-order-btn", "click", async () => {
            const successChangeCard = document.querySelector(".pos-success-card h2");
            const successChangeNote = document.querySelector(".pos-success-card small");
            if (successChangeCard) successChangeCard.textContent = "เงินทอน";
            if (successChangeNote) successChangeNote.textContent = "บาท";
            renderCartPanel(true);
            await loadProducts();
            showScreen("pos");
        });

        on("print-receipt-btn", "click", () => {
            printReceipt(state.lastReceipt);
        });

        document.getElementById("close-session-form").addEventListener("submit", async (event) => {
            event.preventDefault();
            showError("close-session-error", "");
            try {
                const closingCash = Number(document.getElementById("closing-cash").value || 0);
                const data = await rpc("/pos/api/session/close", {
                    token: state.token,
                    closing_cash: closingCash,
                });
                showAlert(
                    `ปิดกะเรียบร้อย\nเงินที่คาดหวัง: ${formatMoney(state.session?.expected_cash || data.expected_cash)} บาท\nส่วนต่าง: ${formatMoney(data.cash_difference)} บาท`,
                    "ปิดกะสำเร็จ"
                );
                state.session = null;
                saveAuth();
                updateSessionHeader();
                showScreen("openSession");
            } catch (error) {
                showError("close-session-error", error.message);
            }
        });

        on("cancel-close-btn", "click", () => {
            showScreen(state.session ? "pos" : "openSession");
        });

        const menuBtn = document.querySelector(".pos-menu-btn");
        if (menuBtn) {
            menuBtn.addEventListener("click", (event) => {
                event.preventDefault();
                event.stopPropagation();
                openDrawer();
            });
        }
        on("close-drawer-btn", "click", closeDrawer);
        const drawerBackdrop = document.getElementById("pos-drawer-backdrop");
        if (drawerBackdrop) {
            drawerBackdrop.addEventListener("click", (event) => {
                if (event.target === drawerBackdrop) closeDrawer();
            });
        }
        const drawer = document.getElementById("pos-drawer");
        if (drawer) {
            drawer.addEventListener("click", (event) => {
                event.stopPropagation();
            });
        }
        document.querySelectorAll("[data-menu]").forEach((button) => {
            button.addEventListener("click", async () => {
                try {
                    await handleMenuAction(button.dataset.menu);
                } catch (error) {
                    showAlert(error.message);
                }
            });
        });

        on("stock-search", "input", debounce(async (event) => {
            state.stockSearch = event.target.value.trim();
            listState.stock.page = 1;
            await loadStock();
        }));

        document.addEventListener("click", async (event) => {
            const button = event.target.closest("[data-page-key][data-page-action]");
            if (!button || button.disabled) return;
            try {
                await changePage(button.dataset.pageKey, button.dataset.pageAction === "next" ? 1 : -1);
            } catch (error) {
                showAlert(error.message);
            }
        });

        async function applySalesDateFilter() {
            dateFilters.sales.date = document.getElementById("sales-date")?.value || "";
            listState.sales.page = 1;
            showError("sales-history-error", "");
            await loadSalesHistory();
        }

        on("sales-filter-btn", "click", applySalesDateFilter);
        on("sales-date", "change", applySalesDateFilter);

        on("sales-history-container", "click", async (event) => {
            const card = event.target.closest("[data-order-id]");
            if (!card) return;
            try {
                await openSalesOrderDetail(Number(card.dataset.orderId));
            } catch (error) {
                showError("sales-history-error", error.message);
            }
        });
        on("sales-detail-back-btn", "click", () => {
            showError("sales-detail-error", "");
            showScreen("salesHistory");
        });

        async function applyRequisitionDateFilter() {
            dateFilters.requisitions.date = document.getElementById("requisition-date")?.value || "";
            listState.requisitions.page = 1;
            showError("requisition-list-error", "");
            await loadRequisitionList();
        }

        on("requisition-filter-btn", "click", applyRequisitionDateFilter);
        on("requisition-date", "change", applyRequisitionDateFilter);

        on("cancel-return-stock", "change", toggleCancelReasonField);
        on("cancel-order-dismiss-btn", "click", closeCancelOrderModal);
        on("cancel-order-confirm-btn", "click", async () => {
            try {
                await submitCancelOrder();
            } catch (error) {
                showError("cancel-order-error", error.message);
            }
        });

        on("requisition-list-btn", "click", async () => {
            await openRequisitionHistoryScreen();
        });
        on("requisition-list-container", "click", async (event) => {
            const card = event.target.closest("[data-requisition-id]");
            if (!card) return;
            try {
                await openRequisitionDetail(Number(card.dataset.requisitionId));
            } catch (error) {
                showError("requisition-list-error", error.message);
            }
        });
        on("requisition-new-btn", "click", async () => {
            await openRequisitionScreen();
        });
        on("requisition-detail-back-btn", "click", async () => {
            await openRequisitionHistoryScreen();
        });
        on("requisition-search", "input", debounce((event) => {
            state.requisitionSearch = event.target.value.trim();
            listState.requisitionProducts.page = 1;
            loadRequisitionProducts().catch((error) => {
                showError("requisition-error", error.message);
            });
        }));
        on("requisition-scan-btn", "click", () => {
            openBarcodeScanner("requisition");
        });
        on("requisition-cart-list", "mousedown", (event) => {
            const button = event.target.closest("[data-req-action='inc'], [data-req-action='dec']");
            if (!button) return;
            event.preventDefault();
        });
        on("requisition-cart-list", "click", (event) => {
            const button = event.target.closest("[data-req-action]");
            if (!button) return;
            updateRequisitionCart(button.dataset.reqAction, Number(button.dataset.id));
        });
        on("requisition-cart-list", "blur", (event) => {
            const input = event.target.closest("[data-req-qty-id]");
            if (!input) return;
            updateRequisitionQty(Number(input.dataset.reqQtyId), input.value);
        });
        on("requisition-cart-list", "keydown", (event) => {
            const input = event.target.closest("[data-req-qty-id]");
            if (!input || event.key !== "Enter") return;
            event.preventDefault();
            updateRequisitionQty(Number(input.dataset.reqQtyId), input.value);
            input.blur();
        });
        on("submit-requisition-btn", "click", async () => {
            try {
                await submitRequisition();
            } catch (error) {
                showError("requisition-error", error.message);
            }
        });
    }

    async function init() {
        bindEvents();
        const saved = loadAuth();
        if (!saved?.token) {
            showScreen("login");
            return;
        }
        state.token = saved.token;
        state.user = saved.user;
        state.session = saved.session || null;
        try {
            const sessionData = await rpc("/pos/api/session/current", { token: state.token });
            state.session = sessionData.session;
            saveAuth();
            if (state.session) {
                await enterPos({ skipSessionFetch: true });
                return;
            }
            showScreen("openSession");
        } catch (error) {
            console.error("POS restore failed:", error);
            if (isAuthError(error.message)) {
                clearAuth();
                showScreen("login");
                return;
            }
            if (state.session) {
                await enterPos({ skipSessionFetch: true });
                return;
            }
            showScreen("openSession");
        }
    }

    document.addEventListener("DOMContentLoaded", init);
})();
