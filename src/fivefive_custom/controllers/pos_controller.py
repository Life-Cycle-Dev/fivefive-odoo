from datetime import datetime, time

from werkzeug.exceptions import NotFound

import pytz

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request


class StorePosController(http.Controller):
    PAGE_SIZE_DEFAULT = 20
    PAGE_SIZE_MAX = 100

    def _json_response(self, ok=True, data=None, error=None):
        return {"ok": ok, "data": data or {}, "error": error}

    def _normalize_page(self, page, page_size):
        page = max(int(page or 1), 1)
        page_size = min(max(int(page_size or self.PAGE_SIZE_DEFAULT), 1), self.PAGE_SIZE_MAX)
        return page, page_size

    def _pagination_meta(self, total, page, page_size):
        total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
        page = min(page, total_pages)
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def _paginate_items(self, items, page, page_size):
        page, page_size = self._normalize_page(page, page_size)
        total = len(items)
        meta = self._pagination_meta(total, page, page_size)
        start = (meta["page"] - 1) * page_size
        return items[start : start + page_size], meta

    def _date_range_domain(self, field_name, date_from=None, date_to=None):
        domain = []
        tz_name = request.env.context.get("tz") or "Asia/Bangkok"
        tz = pytz.timezone(tz_name)

        def utc_bounds(date_str):
            day = datetime.strptime(date_str, "%Y-%m-%d").date()
            start = tz.localize(datetime.combine(day, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
            end = tz.localize(datetime.combine(day, time.max)).astimezone(pytz.UTC).replace(tzinfo=None)
            return start, end

        if date_from:
            start, _ = utc_bounds(date_from)
            domain.append((field_name, ">=", fields.Datetime.to_string(start)))
        if date_to:
            _, end = utc_bounds(date_to)
            domain.append((field_name, "<=", fields.Datetime.to_string(end)))
        return domain

    def _get_pos_user(self, token):
        PosUser = request.env["five.five.store.pos.user"].sudo()
        user = PosUser.get_user_from_token(token)
        if not user:
            raise UserError("Invalid or expired session. Please login again.")
        return user

    def _require_tab(self, user, tab_key):
        user.check_tab_access(tab_key)

    def _serialize_pos_user(self, user):
        return {
            "id": user.id,
            "name": user.name,
            "username": user.username,
            "store_id": user.store_id.id,
            "store_name": user.store_id.name,
            "receipt_settings": self._serialize_store_receipt_settings(user.store_id),
            "tab_permissions": user.get_tab_permissions(),
        }

    def _serialize_product(self, variant, available_qty):
        sell_price = variant.sell_price_thb or 0.0
        return {
            "id": variant.id,
            "name": variant.display_name,
            "sku": variant.sku or "",
            "barcode": variant.barcode or "",
            "sell_price_thb": sell_price,
            "can_sell": sell_price > 0,
            "available_qty": available_qty,
            "image_url": f"/web/image/five.five.product.variant/{variant.id}/image/128"
            if variant.image
            else False,
        }

    @http.route("/pos", type="http", auth="public", website=False, sitemap=False)
    def pos_app(self, **kwargs):
        return request.render("fivefive_custom.store_pos_app", {})

    @http.route("/pos/receipt/<int:order_id>", type="http", auth="user", website=False)
    def pos_receipt_print(self, order_id, **kwargs):
        order = request.env["five.five.store.pos.order"].browse(order_id).exists()
        if not order:
            raise NotFound()
        values = order._get_receipt_print_values()
        return request.render("fivefive_custom.pos_receipt_print_page", values)

    @http.route("/pos/api/login", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_login(self, username, password):
        try:
            PosUser = request.env["five.five.store.pos.user"].sudo()
            result = PosUser.authenticate(username, password)
            if not result:
                return self._json_response(ok=False, error="Invalid username or password.")
            user, token = result
            open_session = request.env["five.five.store.pos.session"].sudo().search(
                [
                    ("pos_user_id", "=", user.id),
                    ("state", "=", "open"),
                ],
                limit=1,
            )
            return self._json_response(
                ok=True,
                data={
                    "token": token,
                    "user": self._serialize_pos_user(user),
                    "open_session_id": open_session.id if open_session else False,
                    "open_session_opening_cash": open_session.opening_cash if open_session else 0.0,
                },
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))
        except Exception as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/logout", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_logout(self, token):
        try:
            user = self._get_pos_user(token)
            open_session = request.env["five.five.store.pos.session"].sudo().search(
                [
                    ("pos_user_id", "=", user.id),
                    ("state", "=", "open"),
                ],
                limit=1,
            )
            if open_session:
                raise UserError("กรุณาปิดกะก่อนออกจากระบบ")
            user.action_logout_token()
            return self._json_response(ok=True)
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/session/open", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_open_session(self, token, opening_cash):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "pos")
            Session = request.env["five.five.store.pos.session"].sudo()
            session = Session.open_session(user, float(opening_cash or 0))
            return self._json_response(
                ok=True,
                data={
                    "session_id": session.id,
                    "opening_cash": session.opening_cash,
                    "opened_at": session.opened_at,
                },
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/session/current", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_current_session(self, token):
        try:
            user = self._get_pos_user(token)
            session = request.env["five.five.store.pos.session"].sudo().search(
                [
                    ("pos_user_id", "=", user.id),
                    ("state", "=", "open"),
                ],
                limit=1,
            )
            user_data = self._serialize_pos_user(user)
            if not session:
                return self._json_response(
                    ok=True,
                    data={
                        "session": False,
                        "user": user_data,
                    },
                )
            return self._json_response(
                ok=True,
                data={
                    "session": {
                        "id": session.id,
                        "opening_cash": session.opening_cash,
                        "total_sales": session.total_sales,
                        "order_count": session.order_count,
                        "opened_at": session.opened_at,
                    },
                    "user": user_data,
                },
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/session/close", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_close_session(self, token, closing_cash):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "close_session")
            session = request.env["five.five.store.pos.session"].sudo().search(
                [
                    ("pos_user_id", "=", user.id),
                    ("state", "=", "open"),
                ],
                limit=1,
            )
            if not session:
                raise UserError("No open session found.")
            session.close_session(float(closing_cash or 0))
            return self._json_response(
                ok=True,
                data={
                    "expected_cash": session.expected_cash,
                    "cash_difference": session.cash_difference,
                },
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/products", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_products(self, token, search="", page=1, page_size=None):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "pos")
            StoreInventory = request.env["five.five.store.inventory"].sudo()
            inventories = StoreInventory.search(
                [
                    ("store_id", "=", user.store_id.id),
                    ("quantity", ">", 0),
                ]
            )
            qty_by_variant = {}
            for inv in inventories:
                qty_by_variant[inv.product_variant_id.id] = qty_by_variant.get(inv.product_variant_id.id, 0) + inv.quantity

            variants = inventories.mapped("product_variant_id").filtered(lambda variant: variant.active)
            search_text = (search or "").strip().lower()
            products = []
            for variant in variants.sorted(key=lambda variant: variant.display_name):
                if search_text and search_text not in (variant.display_name or "").lower() and search_text not in (variant.barcode or "") and search_text not in (variant.sku or "").lower():
                    continue
                products.append(self._serialize_product(variant, qty_by_variant.get(variant.id, 0)))
            page_items, meta = self._paginate_items(products, page, page_size or self.PAGE_SIZE_DEFAULT)
            return self._json_response(ok=True, data={"products": page_items, "pagination": meta})
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    def _get_store_variant_qty(self, store, variant):
        StoreInventory = request.env["five.five.store.inventory"].sudo()
        return sum(
            StoreInventory.search(
                [
                    ("store_id", "=", store.id),
                    ("product_variant_id", "=", variant.id),
                    ("quantity", ">", 0),
                ]
            ).mapped("quantity")
        )

    @http.route("/pos/api/products/barcode", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_product_barcode(self, token, barcode=""):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "pos")
            code = (barcode or "").strip()
            if not code:
                raise UserError("Barcode is required.")
            ProductVariant = request.env["five.five.product.variant"].sudo()
            variant = ProductVariant.search([("barcode", "=", code), ("active", "=", True)], limit=1)
            if not variant:
                variant = ProductVariant.search([("sku", "=", code), ("active", "=", True)], limit=1)
            if not variant:
                raise UserError("Product not found for this barcode.")
            available_qty = self._get_store_variant_qty(user.store_id, variant)
            if available_qty <= 0:
                raise UserError("This product is not available in store inventory.")
            return self._json_response(
                ok=True,
                data={"product": self._serialize_product(variant, available_qty)},
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/order/create", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_create_order(
        self,
        token,
        lines,
        discount_type=None,
        discount_value=0,
        amount_paid=0,
        payment_method="cash",
        transfer_slip=None,
        transfer_slip_filename=None,
    ):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "pos")
            session = request.env["five.five.store.pos.session"].sudo().search(
                [
                    ("pos_user_id", "=", user.id),
                    ("state", "=", "open"),
                ],
                limit=1,
            )
            if not session:
                raise UserError("Please open a session before creating orders.")
            Order = request.env["five.five.store.pos.order"].sudo()
            order = Order.create_order(
                session,
                user,
                lines or [],
                discount_type=discount_type,
                discount_value=float(discount_value or 0),
                amount_paid=float(amount_paid or 0),
                payment_method=payment_method or "cash",
                transfer_slip=transfer_slip,
                transfer_slip_filename=transfer_slip_filename,
            )
            return self._json_response(
                ok=True,
                data={
                    "order": {
                        **self._serialize_order(order),
                        "store_name": user.store_id.name,
                        "cashier_name": user.name,
                        "receipt_settings": self._serialize_store_receipt_settings(user.store_id),
                    }
                },
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    def _serialize_store_receipt_settings(self, store):
        return store.get_pos_receipt_settings()

    def _serialize_order(self, order):
        return {
            "id": order.id,
            "number": order.number,
            "order_date": order.order_date,
            "state": order.state,
            "subtotal": order.subtotal,
            "discount_amount": order.discount_amount,
            "total": order.total,
            "amount_paid": order.amount_paid,
            "change_amount": order.change_amount,
            "payment_method": order.payment_method,
            "return_stock": order.return_stock,
            "cancel_reason": order.cancel_reason or "",
            "cancelled_at": order.cancelled_at,
            "can_cancel": order.state == "done",
            "lines": [
                {
                    "product_name": line.product_variant_id.display_name,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "subtotal": line.subtotal,
                }
                for line in order.line_ids
            ],
        }

    def _serialize_order_detail(self, order):
        data = self._serialize_order(order)
        data.update(
            {
                "store_name": order.store_id.name,
                "cashier_name": order.pos_user_id.name,
                "discount_type": order.discount_type,
                "discount_value": order.discount_value,
                "cancelled_at": order.cancelled_at,
                "receipt_settings": self._serialize_store_receipt_settings(order.store_id),
            }
        )
        return data

    @http.route("/pos/api/orders/list", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_orders_list(self, token, page=1, page_size=None, date_from=None, date_to=None, search=""):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "sales")
            Order = request.env["five.five.store.pos.order"].sudo()
            domain = [("store_id", "=", user.store_id.id)]
            search_text = (search or "").strip()
            if search_text:
                domain.append(("number", "ilike", f"%{search_text}%"))
            else:
                domain.extend(self._date_range_domain("order_date", date_from, date_to))
            page, page_size = self._normalize_page(page, page_size or self.PAGE_SIZE_DEFAULT)
            total = Order.search_count(domain)
            meta = self._pagination_meta(total, page, page_size)
            orders = Order.search(
                domain,
                order="order_date desc, id desc",
                limit=page_size,
                offset=(meta["page"] - 1) * page_size,
            )
            return self._json_response(
                ok=True,
                data={
                    "orders": [self._serialize_order(order) for order in orders],
                    "pagination": meta,
                },
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/orders/detail", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_orders_detail(self, token, order_id):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "sales")
            order = request.env["five.five.store.pos.order"].sudo().browse(int(order_id)).exists()
            if not order or order.store_id.id != user.store_id.id:
                raise UserError("Order not found.")
            return self._json_response(ok=True, data={"order": self._serialize_order_detail(order)})
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/orders/cancel", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_orders_cancel(self, token, order_id, return_stock=False, cancel_reason=""):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "sales")
            order = request.env["five.five.store.pos.order"].sudo().browse(int(order_id)).exists()
            if not order or order.store_id.id != user.store_id.id:
                raise UserError("Order not found.")
            order.action_cancel_from_pos(return_stock=bool(return_stock), cancel_reason=cancel_reason)
            return self._json_response(ok=True, data={"order": self._serialize_order(order)})
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/stock", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_stock(self, token, search="", page=1, page_size=None):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "stock")
            StoreInventory = request.env["five.five.store.inventory"].sudo()
            inventories = StoreInventory.search(
                [
                    ("store_id", "=", user.store_id.id),
                    ("quantity", ">", 0),
                ],
                order="product_variant_id, lot_number",
            )
            search_text = (search or "").strip().lower()
            qty_by_variant = {}
            for inv in inventories:
                variant = inv.product_variant_id
                name = variant.display_name or ""
                if search_text and search_text not in name.lower() and search_text not in (inv.lot_number or ""):
                    continue
                qty_by_variant[variant.id] = {
                    "product_name": name,
                    "total_qty": qty_by_variant.get(variant.id, {}).get("total_qty", 0) + inv.quantity,
                    "sell_price_thb": variant.sell_price_thb or 0.0,
                }
            summary = sorted(qty_by_variant.values(), key=lambda row: row["product_name"])
            page_items, meta = self._paginate_items(summary, page, page_size or self.PAGE_SIZE_DEFAULT)
            return self._json_response(
                ok=True,
                data={"summary": page_items, "pagination": meta},
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    def _serialize_requisition_line(self, line):
        movements = line.requisition_id.movement_ids.filtered(
            lambda movement: movement.requisition_line_id.id == line.id
            and movement.state != "cancelled"
        )
        return {
            "product_name": line.product_variant_id.display_name,
            "requested_qty": line.requested_qty,
            "allocated_qty": line.allocated_qty,
            "allocations": [
                {
                    "warehouse_name": movement.warehouse_id.name or "",
                    "lot_number": movement.lot_number or "",
                    "quantity": movement.quantity,
                }
                for movement in movements
            ],
        }

    def _serialize_requisition(self, requisition, include_lines=False):
        lines = requisition.line_ids
        data = {
            "id": requisition.id,
            "number": requisition.number,
            "state": requisition.state,
            "warehouse_name": ", ".join(requisition.warehouse_ids.mapped("name"))
            or (requisition.warehouse_id.name or ""),
            "warehouse_names": requisition.warehouse_ids.mapped("name"),
            "note": requisition.note or "",
            "requested_at": requisition.requested_at,
            "prepared_at": requisition.prepared_at,
            "received_at": requisition.received_at,
            "done_at": requisition.done_at,
            "line_count": len(lines),
            "can_mark_received": requisition.state == "prepared",
            "items_preview": " · ".join(lines.mapped("product_variant_id.display_name")[:3]),
        }
        if include_lines:
            data["lines"] = [self._serialize_requisition_line(line) for line in lines]
        return data

    @http.route("/pos/api/requisition/products", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_requisition_products(self, token, search="", page=1, page_size=None):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "requisition")
            variants = request.env["five.five.product.variant"].sudo().search(
                [("active", "=", True)],
                order="name, id",
            )
            search_text = (search or "").strip().lower()
            products = []
            for variant in variants:
                name = (variant.display_name or "").lower()
                barcode = variant.barcode or ""
                sku = (variant.sku or "").lower()
                if search_text and search_text not in name and search_text not in barcode and search_text not in sku:
                    continue
                sell_price = variant.sell_price_thb or 0.0
                products.append(
                    {
                        "id": variant.id,
                        "name": variant.display_name,
                        "sku": variant.sku or "",
                        "barcode": barcode,
                        "sell_price_thb": sell_price,
                        "has_sell_price": sell_price > 0,
                    }
                )
            page_items, meta = self._paginate_items(products, page, page_size or self.PAGE_SIZE_DEFAULT)
            return self._json_response(ok=True, data={"products": page_items, "pagination": meta})
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/requisition/create", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_requisition_create(self, token, lines, note=""):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "requisition")
            session = request.env["five.five.store.pos.session"].sudo().search(
                [
                    ("pos_user_id", "=", user.id),
                    ("state", "=", "open"),
                ],
                limit=1,
            )
            Requisition = request.env["five.five.store.requisition"].sudo()
            requisition = Requisition.create_from_pos(
                user,
                lines or [],
                note=note,
                session=session,
            )
            return self._json_response(
                ok=True,
                data={
                    "requisition": self._serialize_requisition(requisition, include_lines=True),
                },
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/requisition/list", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_requisition_list(self, token, page=1, page_size=None, date_from=None, date_to=None):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "requisition_history")
            domain = [("pos_user_id", "=", user.id)]
            domain.extend(self._date_range_domain("requested_at", date_from, date_to))
            Requisition = request.env["five.five.store.requisition"].sudo()
            page, page_size = self._normalize_page(page, page_size or self.PAGE_SIZE_DEFAULT)
            total = Requisition.search_count(domain)
            meta = self._pagination_meta(total, page, page_size)
            requisitions = Requisition.search(
                domain,
                order="requested_at desc",
                limit=page_size,
                offset=(meta["page"] - 1) * page_size,
            )
            return self._json_response(
                ok=True,
                data={
                    "requisitions": [self._serialize_requisition(req) for req in requisitions],
                    "pagination": meta,
                },
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/requisition/detail", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_requisition_detail(self, token, requisition_id):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "requisition_history")
            requisition = (
                request.env["five.five.store.requisition"]
                .sudo()
                .browse(int(requisition_id))
                .exists()
            )
            if not requisition or requisition.pos_user_id.id != user.id:
                raise UserError("Requisition not found.")
            return self._json_response(
                ok=True,
                data={"requisition": self._serialize_requisition(requisition, include_lines=True)},
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/requisition/received", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_requisition_received(self, token, requisition_id):
        try:
            user = self._get_pos_user(token)
            self._require_tab(user, "requisition_history")
            requisition = request.env["five.five.store.requisition"].sudo().browse(int(requisition_id)).exists()
            if not requisition or requisition.pos_user_id.id != user.id:
                raise UserError("Requisition not found.")
            requisition.action_mark_received()
            return self._json_response(ok=True, data={"state": requisition.state})
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))
