from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


class StorePosController(http.Controller):

    def _json_response(self, ok=True, data=None, error=None):
        return {"ok": ok, "data": data or {}, "error": error}

    def _get_pos_user(self, token):
        PosUser = request.env["five.five.store.pos.user"].sudo()
        user = PosUser.get_user_from_token(token)
        if not user:
            raise UserError("Invalid or expired session. Please login again.")
        return user

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
                    "user": {
                        "id": user.id,
                        "name": user.name,
                        "username": user.username,
                        "store_id": user.store_id.id,
                        "store_name": user.store_id.name,
                    },
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
            user.action_logout_token()
            return self._json_response(ok=True)
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/session/open", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_open_session(self, token, opening_cash):
        try:
            user = self._get_pos_user(token)
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
            if not session:
                return self._json_response(ok=True, data={"session": False})
            return self._json_response(
                ok=True,
                data={
                    "session": {
                        "id": session.id,
                        "opening_cash": session.opening_cash,
                        "total_sales": session.total_sales,
                        "order_count": session.order_count,
                        "opened_at": session.opened_at,
                    }
                },
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/session/close", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_close_session(self, token, closing_cash):
        try:
            user = self._get_pos_user(token)
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
    def pos_products(self, token, search=""):
        try:
            user = self._get_pos_user(token)
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
                if search_text and search_text not in (variant.display_name or "").lower() and search_text not in (variant.barcode or ""):
                    continue
                products.append(self._serialize_product(variant, qty_by_variant.get(variant.id, 0)))
            return self._json_response(ok=True, data={"products": products})
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/order/create", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_create_order(self, token, lines, discount_type=None, discount_value=0, amount_paid=0):
        try:
            user = self._get_pos_user(token)
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
            )
            return self._json_response(
                ok=True,
                data={
                    "order": {
                        "id": order.id,
                        "number": order.number,
                        "subtotal": order.subtotal,
                        "discount_amount": order.discount_amount,
                        "total": order.total,
                        "amount_paid": order.amount_paid,
                        "change_amount": order.change_amount,
                    }
                },
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

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

    @http.route("/pos/api/orders/list", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_orders_list(self, token, limit=50):
        try:
            user = self._get_pos_user(token)
            Order = request.env["five.five.store.pos.order"].sudo()
            orders = Order.search(
                [("store_id", "=", user.store_id.id)],
                order="order_date desc, id desc",
                limit=min(int(limit or 50), 100),
            )
            return self._json_response(
                ok=True,
                data={"orders": [self._serialize_order(order) for order in orders]},
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/orders/cancel", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_orders_cancel(self, token, order_id, return_stock=False, cancel_reason=""):
        try:
            user = self._get_pos_user(token)
            order = request.env["five.five.store.pos.order"].sudo().browse(int(order_id)).exists()
            if not order or order.store_id.id != user.store_id.id:
                raise UserError("Order not found.")
            order.action_cancel_from_pos(return_stock=bool(return_stock), cancel_reason=cancel_reason)
            return self._json_response(ok=True, data={"order": self._serialize_order(order)})
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/stock", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_stock(self, token, search=""):
        try:
            user = self._get_pos_user(token)
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
            items = []
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
                items.append(
                    {
                        "id": inv.id,
                        "product_name": name,
                        "lot_number": inv.lot_number or "",
                        "quantity": inv.quantity,
                        "sell_price_thb": variant.sell_price_thb or 0.0,
                        "quality_note": inv.quality_note or "",
                    }
                )
            summary = sorted(qty_by_variant.values(), key=lambda row: row["product_name"])
            return self._json_response(
                ok=True,
                data={"items": items, "summary": summary},
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/requisition/products", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_requisition_products(self, token, search=""):
        try:
            self._get_pos_user(token)
            variants = request.env["five.five.product.variant"].sudo().search(
                [
                    ("active", "=", True),
                    ("sell_price_thb", ">", 0),
                ],
                order="name, id",
            )
            search_text = (search or "").strip().lower()
            products = []
            for variant in variants:
                if search_text and search_text not in (variant.display_name or "").lower() and search_text not in (variant.barcode or ""):
                    continue
                products.append(
                    {
                        "id": variant.id,
                        "name": variant.display_name,
                        "sku": variant.sku or "",
                        "barcode": variant.barcode or "",
                        "sell_price_thb": variant.sell_price_thb,
                        "image_url": f"/web/image/five.five.product.variant/{variant.id}/image/128"
                        if variant.image
                        else False,
                    }
                )
            return self._json_response(ok=True, data={"products": products})
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/requisition/create", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_requisition_create(self, token, lines, note=""):
        try:
            user = self._get_pos_user(token)
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
                    "requisition": {
                        "id": requisition.id,
                        "number": requisition.number,
                        "state": requisition.state,
                    }
                },
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/requisition/list", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_requisition_list(self, token):
        try:
            user = self._get_pos_user(token)
            requisitions = request.env["five.five.store.requisition"].sudo().search(
                [("pos_user_id", "=", user.id)],
                order="requested_at desc",
                limit=50,
            )
            return self._json_response(
                ok=True,
                data={
                    "requisitions": [
                        {
                            "id": req.id,
                            "number": req.number,
                            "state": req.state,
                            "warehouse_name": req.warehouse_id.name or "",
                            "requested_at": req.requested_at,
                            "line_count": len(req.line_ids),
                            "can_mark_received": req.state == "prepared",
                        }
                        for req in requisitions
                    ]
                },
            )
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))

    @http.route("/pos/api/requisition/received", type="json", auth="public", csrf=False, methods=["POST"])
    def pos_requisition_received(self, token, requisition_id):
        try:
            user = self._get_pos_user(token)
            requisition = request.env["five.five.store.requisition"].sudo().browse(int(requisition_id)).exists()
            if not requisition or requisition.pos_user_id.id != user.id:
                raise UserError("Requisition not found.")
            requisition.action_mark_received()
            return self._json_response(ok=True, data={"state": requisition.state})
        except UserError as exc:
            return self._json_response(ok=False, error=str(exc))
