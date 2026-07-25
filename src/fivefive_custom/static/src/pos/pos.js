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
        orderNote: "",
        search: "",
        requisitionProducts: [],
        requisitionCart: [],
        requisitionSearch: "",
        stockSearch: "",
        cancelOrderId: null,
        salesOrders: [],
        stockItems: [],
        lastOrder: null,
    };

    const orderStateLabels = {
        done: "สำเร็จ",
        cancelled: "ยกเลิก",
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
        stock: document.getElementById("screen-stock"),
        salesHistory: document.getElementById("screen-sales-history"),
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
        const actions = editable
            ? `<div class="pos-cart-row-actions">
                <button type="button" class="pos-mini-btn" data-action="dec" data-id="${line.id}">−</button>
                <button type="button" class="pos-mini-btn" data-action="inc" data-id="${line.id}">+</button>
                <button type="button" class="pos-mini-btn" data-action="remove" data-id="${line.id}">×</button>
               </div>`
            : "";
        return `
            <div class="pos-cart-row">
                <div>${formatMoney(line.quantity)}</div>
                <div>
                    <div class="pos-cart-row-name">${line.name}</div>
                    <div class="pos-cart-row-sub">${formatMoney(line.unit_price)} / ชิ้น</div>
                    ${actions}
                </div>
                <div class="pos-cart-row-price">${formatMoney(lineTotal)}</div>
            </div>`;
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
        if (checkoutBtn) checkoutBtn.disabled = !state.cart.length;

        updateAmountDisplay();
    }

    function renderProducts() {
        const grid = document.getElementById("product-grid");
        if (!grid) return;
        grid.innerHTML = "";
        const filtered = state.products.filter((product) => {
            if (!state.search) return true;
            const text = state.search.toLowerCase();
            return (
                (product.name || "").toLowerCase().includes(text) ||
                (product.barcode || "").includes(text) ||
                (product.sku || "").toLowerCase().includes(text)
            );
        });
        if (!filtered.length) {
            grid.innerHTML = '<div class="pos-empty">ไม่มีสินค้าในสต็อกร้าน</div>';
            return;
        }
        filtered.forEach((product) => {
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
                <div class="pos-product-meta">คงเหลือ ${formatMoney(product.available_qty)}</div>
                ${priceHtml}
            `;
            button.addEventListener("click", () => {
                if (!product.can_sell) {
                    alert("สินค้านี้ยังไม่ได้ตั้งราคาขาย กรุณาตั้ง Sell Price (THB) ที่ Product Variant");
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
                available_qty: product.available_qty,
                quantity: 1,
            });
        }
        renderCartPanel(true);
    }

    function addByBarcode() {
        const input = document.getElementById("barcode-input");
        if (!input) return;
        const code = input.value.trim();
        if (!code) return;
        const product = findProductByBarcode(code);
        if (!product) {
            alert("ไม่พบสินค้าจากบาร์โค้ดนี้");
            return;
        }
        if (!product.can_sell) {
            alert("สินค้านี้ยังไม่ได้ตั้งราคาขาย กรุณาตั้ง Sell Price (THB) ที่ Product Variant");
            return;
        }
        addToCart(product);
        input.value = "";
        input.focus();
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
        const totals = computeTotals();
        if (key === "clear") {
            state.amountPaidInput = "";
        } else if (key === "exact") {
            state.amountPaidInput = String(Math.ceil(totals.total * 100) / 100);
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

    function openPaymentScreen() {
        state.amountPaidInput = "";
        showError("checkout-error", "");
        renderCartPanel(false);
        updateAmountDisplay();
        showScreen("payment");
    }

    function openDiscountScreen() {
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
        const totals = computeTotals();
        if (totals.amountPaid < totals.total) {
            showError("checkout-error", "จำนวนเงินที่รับต้องไม่น้อยกว่ายอดชำระ");
            return;
        }
        document.getElementById("modal-total").textContent = formatMoney(totals.total);
        document.getElementById("modal-paid").textContent = formatMoney(totals.amountPaid);
        document.getElementById("modal-change").textContent = formatMoney(totals.changeAmount);
        document.getElementById("pay-confirm-modal").classList.add("show");
    }

    function hidePayConfirmModal() {
        document.getElementById("pay-confirm-modal").classList.remove("show");
    }

    async function loadProducts() {
        const data = await rpc("/pos/api/products", {
            token: state.token,
            search: state.search,
        });
        state.products = data.products || [];
        renderProducts();
    }

    function renderRequisitionProducts() {
        const grid = document.getElementById("requisition-product-grid");
        if (!grid) return;
        grid.innerHTML = "";
        const filtered = state.requisitionProducts.filter((product) => {
            if (!state.requisitionSearch) return true;
            const text = state.requisitionSearch.toLowerCase();
            return (product.name || "").toLowerCase().includes(text) || (product.barcode || "").includes(text);
        });
        if (!filtered.length) {
            grid.innerHTML = '<div class="pos-empty">ไม่พบสินค้า</div>';
            return;
        }
        filtered.forEach((product) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "pos-product";
            button.innerHTML = `
                ${product.image_url ? `<img class="pos-product-image" src="${product.image_url}" alt="">` : `<div class="pos-product-image-empty"></div>`}
                <div class="pos-product-name">${product.name}</div>
                <div class="pos-product-price">${formatMoney(product.sell_price_thb)}</div>
            `;
            button.addEventListener("click", () => addToRequisitionCart(product));
            grid.appendChild(button);
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
                const item = document.createElement("div");
                item.className = "pos-line-item";
                item.innerHTML = `
                    <div>
                        <strong>${line.name}</strong>
                        <div class="pos-cart-row-actions" style="margin-top:6px;">
                            <button type="button" class="pos-mini-btn" data-req-action="dec" data-id="${line.id}">−</button>
                            <span style="padding:0 8px;">${formatMoney(line.quantity)}</span>
                            <button type="button" class="pos-mini-btn" data-req-action="inc" data-id="${line.id}">+</button>
                            <button type="button" class="pos-mini-btn" data-req-action="remove" data-id="${line.id}">×</button>
                        </div>
                    </div>
                `;
                list.appendChild(item);
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
        });
        state.requisitionProducts = data.products || [];
        renderRequisitionProducts();
    }

    async function submitRequisition() {
        showError("requisition-error", "");
        const success = document.getElementById("requisition-success");
        if (success) {
            success.hidden = true;
            success.textContent = "";
        }
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
        if (success) {
            success.hidden = false;
            success.textContent = `ส่งคำขอเบิก ${result.requisition.number} เรียบร้อยแล้ว`;
        }
    }

    async function loadRequisitionList() {
        const container = document.getElementById("requisition-list-container");
        if (!container) return;
        const data = await rpc("/pos/api/requisition/list", { token: state.token });
        const rows = data.requisitions || [];
        if (!rows.length) {
            container.innerHTML = '<div class="pos-empty">ยังไม่มีรายการเบิก</div>';
            return;
        }
        container.innerHTML = rows
            .map(
                (row) => `
                <div class="pos-line-item">
                    <div>
                        <strong>${row.number}</strong>
                        <div class="pos-product-meta">${stateLabels[row.state] || row.state}</div>
                        ${row.warehouse_name ? `<div class="pos-product-meta">จาก: ${row.warehouse_name}</div>` : ""}
                        <div class="pos-product-meta">${row.line_count} รายการ</div>
                        ${
                            row.can_mark_received
                                ? `<button type="button" class="pos-btn pos-btn-primary" data-received-id="${row.id}">รับสินค้าแล้ว</button>`
                                : ""
                        }
                    </div>
                </div>`
            )
            .join("");
        container.querySelectorAll("[data-received-id]").forEach((button) => {
            button.addEventListener("click", async () => {
                try {
                    await rpc("/pos/api/requisition/received", {
                        token: state.token,
                        requisition_id: Number(button.dataset.receivedId),
                    });
                    await loadRequisitionList();
                } catch (error) {
                    alert(error.message);
                }
            });
        });
    }

    async function openRequisitionScreen() {
        state.requisitionCart = [];
        state.requisitionSearch = "";
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
            showScreen("pos");
            return;
        }
        if (action === "close-session") {
            document.getElementById("closing-cash").value = "";
            showError("close-session-error", "");
            showScreen("closeSession");
            return;
        }
        if (action === "requisition") {
            await openRequisitionScreen();
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
        });
        state.stockItems = data.items || [];
        renderStock();
    }

    function renderStock() {
        const summaryEl = document.getElementById("stock-summary");
        const container = document.getElementById("stock-list-container");
        if (!summaryEl || !container) return;

        const summary = {};
        state.stockItems.forEach((item) => {
            if (!summary[item.product_name]) {
                summary[item.product_name] = { qty: 0, price: item.sell_price_thb };
            }
            summary[item.product_name].qty += Number(item.quantity || 0);
        });
        const summaryRows = Object.entries(summary);
        if (!summaryRows.length) {
            summaryEl.innerHTML = '<div class="pos-empty" style="padding:12px;">ไม่มีสต็อกในร้าน</div>';
            container.innerHTML = "";
            return;
        }
        summaryEl.innerHTML = `
            <div style="font-weight:700;margin-bottom:8px;">สรุปสต็อก</div>
            ${summaryRows
                .map(
                    ([name, row]) => `
                <div class="pos-summary-row">
                    <span>${name}</span>
                    <span>${formatMoney(row.qty)} ชิ้น · ${formatMoney(row.price)} บาท</span>
                </div>`
                )
                .join("")}
        `;
        container.innerHTML = `
            <table class="pos-stock-table">
                <thead>
                    <tr>
                        <th>สินค้า</th>
                        <th>Lot</th>
                        <th>จำนวน</th>
                        <th>ราคาขาย</th>
                        <th>หมายเหตุ</th>
                    </tr>
                </thead>
                <tbody>
                    ${state.stockItems
                        .map(
                            (item) => `
                        <tr>
                            <td>${item.product_name}</td>
                            <td>${item.lot_number || "-"}</td>
                            <td>${formatMoney(item.quantity)}</td>
                            <td>${formatMoney(item.sell_price_thb)}</td>
                            <td>${item.quality_note || "-"}</td>
                        </tr>`
                        )
                        .join("")}
                </tbody>
            </table>`;
    }

    async function openStockScreen() {
        state.stockSearch = "";
        const search = document.getElementById("stock-search");
        if (search) search.value = "";
        await loadStock();
        showScreen("stock");
    }

    async function loadSalesHistory() {
        const data = await rpc("/pos/api/orders/list", { token: state.token, limit: 50 });
        state.salesOrders = data.orders || [];
        renderSalesHistory();
    }

    function renderSalesHistory() {
        const container = document.getElementById("sales-history-container");
        if (!container) return;
        if (!state.salesOrders.length) {
            container.innerHTML = '<div class="pos-empty">ยังไม่มีประวัติการขาย</div>';
            return;
        }
        container.innerHTML = state.salesOrders
            .map((order) => {
                const badgeClass = order.state === "cancelled" ? "pos-badge-cancelled" : "pos-badge-done";
                const linesHtml = (order.lines || [])
                    .map(
                        (line) =>
                            `<div class="pos-product-meta">${line.product_name} × ${formatMoney(line.quantity)} = ${formatMoney(line.subtotal)}</div>`
                    )
                    .join("");
                const cancelInfo =
                    order.state === "cancelled"
                        ? `<div class="pos-product-meta">${
                              order.return_stock ? "คืนสต็อกแล้ว" : "ไม่คืนสต็อก"
                          }${order.cancel_reason ? ` · ${order.cancel_reason}` : ""}</div>`
                        : "";
                return `
                <div class="pos-list-card">
                    <div class="pos-list-card-head">
                        <div>
                            <div class="pos-list-card-title">${order.number}</div>
                            <div class="pos-product-meta">${formatDateTime(order.order_date)}</div>
                        </div>
                        <span class="pos-badge ${badgeClass}">${orderStateLabels[order.state] || order.state}</span>
                    </div>
                    ${linesHtml}
                    <div class="pos-summary-row" style="margin-top:8px;">
                        <span>ยอดชำระ</span>
                        <strong>${formatMoney(order.total)} บาท</strong>
                    </div>
                    ${cancelInfo}
                    ${
                        order.can_cancel
                            ? `<button type="button" class="pos-btn pos-btn-danger pos-btn-sm" style="margin-top:10px;" data-cancel-order-id="${order.id}">ยกเลิกรายการ</button>`
                            : ""
                    }
                </div>`;
            })
            .join("");

        container.querySelectorAll("[data-cancel-order-id]").forEach((button) => {
            button.addEventListener("click", () => {
                const order = state.salesOrders.find((row) => row.id === Number(button.dataset.cancelOrderId));
                if (order) openCancelOrderModal(order);
            });
        });
    }

    async function openSalesHistoryScreen() {
        showError("sales-history-error", "");
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
        closeCancelOrderModal();
        await loadSalesHistory();
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
        document.getElementById("pos-session-badge").textContent = state.session.id;
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
        if (totals.amountPaid < totals.total) {
            showError("checkout-error", "จำนวนเงินที่รับต้องไม่น้อยกว่ายอดชำระ");
            return;
        }
        const lines = state.cart.map((line) => ({
            product_variant_id: line.id,
            quantity: line.quantity,
        }));
        const result = await rpc("/pos/api/order/create", {
            token: state.token,
            lines,
            discount_type: state.discountValue > 0 ? state.discountType : null,
            discount_value: state.discountValue,
            amount_paid: totals.amountPaid,
        });
        state.lastOrder = result.order;
        document.getElementById("success-order-number").textContent = result.order.number;
        document.getElementById("success-subtotal").textContent = formatMoney(result.order.subtotal);
        document.getElementById("success-discount").textContent = formatMoney(result.order.discount_amount);
        document.getElementById("success-total").textContent = formatMoney(result.order.total);
        document.getElementById("success-paid").textContent = formatMoney(result.order.amount_paid);
        document.getElementById("success-change").textContent = formatMoney(result.order.change_amount);
        state.cart = [];
        state.discountValue = 0;
        state.discountType = "percent";
        state.amountPaidInput = "";
        state.orderNote = "";
        hidePayConfirmModal();
        await loadProducts();
        showScreen("success");
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

        document.addEventListener("click", (event) => {
            if (event.target.closest("#pos-menu-btn")) {
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
            renderProducts();
        });

        document.getElementById("cart-list").addEventListener("click", (event) => {
            const button = event.target.closest("[data-action]");
            if (!button) return;
            updateCart(button.dataset.action, Number(button.dataset.id));
        });

        document.getElementById("barcode-add-btn").addEventListener("click", addByBarcode);
        document.getElementById("barcode-input").addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                addByBarcode();
            }
        });

        document.getElementById("checkout-btn").addEventListener("click", openDiscountScreen);

        document.getElementById("back-to-pos-btn").addEventListener("click", () => {
            renderCartPanel(true);
            showScreen("pos");
        });

        document.getElementById("to-payment-btn").addEventListener("click", openPaymentScreen);

        document.getElementById("back-to-discount-btn").addEventListener("click", () => {
            renderCartPanel(false);
            showScreen("discount");
        });

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

        document.getElementById("new-order-btn").addEventListener("click", async () => {
            renderCartPanel(true);
            await loadProducts();
            showScreen("pos");
        });

        document.getElementById("close-session-btn").addEventListener("click", () => {
            document.getElementById("closing-cash").value = "";
            showError("close-session-error", "");
            showScreen("closeSession");
        });

        document.getElementById("cancel-close-btn").addEventListener("click", () => showScreen("pos"));

        document.getElementById("close-session-form").addEventListener("submit", async (event) => {
            event.preventDefault();
            showError("close-session-error", "");
            try {
                const closingCash = Number(document.getElementById("closing-cash").value || 0);
                const data = await rpc("/pos/api/session/close", {
                    token: state.token,
                    closing_cash: closingCash,
                });
                alert(
                    `ปิดกะเรียบร้อย\nเงินที่คาดหวัง: ${formatMoney(state.session?.expected_cash || data.expected_cash)} บาท\nส่วนต่าง: ${formatMoney(data.cash_difference)} บาท`
                );
                await rpc("/pos/api/logout", { token: state.token });
                clearAuth();
                showScreen("login");
            } catch (error) {
                showError("close-session-error", error.message);
            }
        });

        document.getElementById("logout-btn").addEventListener("click", async () => {
            if (state.token) {
                try {
                    await rpc("/pos/api/logout", { token: state.token });
                } catch (_error) {
                    // ignore
                }
            }
            clearAuth();
            showScreen("login");
        });

        const menuBtn = document.getElementById("pos-menu-btn");
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
                    alert(error.message);
                }
            });
        });

        on("back-from-stock-btn", "click", () => showScreen("pos"));
        on("back-from-sales-btn", "click", () => showScreen("pos"));
        on("stock-search", "input", async (event) => {
            state.stockSearch = event.target.value.trim();
            await loadStock();
        });

        on("cancel-return-stock", "change", toggleCancelReasonField);
        on("cancel-order-dismiss-btn", "click", closeCancelOrderModal);
        on("cancel-order-confirm-btn", "click", async () => {
            try {
                await submitCancelOrder();
            } catch (error) {
                showError("cancel-order-error", error.message);
            }
        });

        document.getElementById("back-from-requisition-btn").addEventListener("click", () => showScreen("pos"));
        document.getElementById("requisition-list-btn").addEventListener("click", async () => {
            await loadRequisitionList();
            showScreen("requisitionList");
        });
        document.getElementById("back-from-requisition-list-btn").addEventListener("click", () => showScreen("requisition"));
        document.getElementById("requisition-search").addEventListener("input", (event) => {
            state.requisitionSearch = event.target.value.trim();
            renderRequisitionProducts();
        });
        document.getElementById("requisition-cart-list").addEventListener("click", (event) => {
            const button = event.target.closest("[data-req-action]");
            if (!button) return;
            updateRequisitionCart(button.dataset.reqAction, Number(button.dataset.id));
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
