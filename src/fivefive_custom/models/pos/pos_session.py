from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StorePosSession(models.Model):
    _name = "five.five.store.pos.session"
    _description = "Store POS Session"
    _order = "opened_at desc, id desc"

    name = fields.Char(string="Session", compute="_compute_name", store=True)
    store_id = fields.Many2one("five.five.store", required=True, index=True)
    pos_user_id = fields.Many2one("five.five.store.pos.user", required=True, index=True)
    state = fields.Selection(
        [("open", "Open"), ("closed", "Closed")],
        default="open",
        required=True,
        index=True,
    )
    opening_cash = fields.Float(string="Opening Cash (THB)", digits=(16, 2))
    closing_cash = fields.Float(string="Closing Cash (THB)", digits=(16, 2))
    expected_cash = fields.Float(
        string="Expected Cash (THB)",
        compute="_compute_session_totals",
        store=True,
        digits=(16, 2),
    )
    cash_difference = fields.Float(
        string="Cash Difference (THB)",
        compute="_compute_session_totals",
        store=True,
        digits=(16, 2),
    )
    opened_at = fields.Datetime(string="Opened At", default=fields.Datetime.now, required=True)
    closed_at = fields.Datetime(string="Closed At")
    order_ids = fields.One2many("five.five.store.pos.order", "session_id", string="Orders")
    order_count = fields.Integer(compute="_compute_session_totals", store=True)
    total_sales = fields.Float(
        string="Total Sales (THB)",
        compute="_compute_session_totals",
        store=True,
        digits=(16, 2),
    )

    @api.depends("store_id.name", "pos_user_id.username", "opened_at")
    def _compute_name(self):
        for session in self:
            store_name = session.store_id.name or "-"
            user_name = session.pos_user_id.username or "-"
            opened = fields.Datetime.to_string(session.opened_at) if session.opened_at else ""
            session.name = f"{store_name} / {user_name} / {opened}"

    @api.depends("opening_cash", "closing_cash", "order_ids.total", "order_ids.state")
    def _compute_session_totals(self):
        for session in self:
            done_orders = session.order_ids.filtered(lambda order: order.state == "done")
            total_sales = sum(done_orders.mapped("total"))
            session.total_sales = total_sales
            session.order_count = len(done_orders)
            session.expected_cash = session.opening_cash + total_sales
            if session.state == "closed":
                session.cash_difference = session.closing_cash - session.expected_cash
            else:
                session.cash_difference = 0.0

    @api.model
    def open_session(self, pos_user, opening_cash):
        existing = self.search(
            [
                ("store_id", "=", pos_user.store_id.id),
                ("pos_user_id", "=", pos_user.id),
                ("state", "=", "open"),
            ],
            limit=1,
        )
        if existing:
            raise UserError(_("You already have an open session."))
        if float_compare(opening_cash, 0, precision_digits=2) < 0:
            raise UserError(_("Opening cash must be zero or greater."))
        return self.create(
            {
                "store_id": pos_user.store_id.id,
                "pos_user_id": pos_user.id,
                "opening_cash": opening_cash,
                "state": "open",
            }
        )

    def close_session(self, closing_cash):
        self.ensure_one()
        if self.state != "open":
            raise UserError(_("This session is already closed."))
        if float_compare(closing_cash, 0, precision_digits=2) < 0:
            raise UserError(_("Closing cash must be zero or greater."))
        self.write(
            {
                "closing_cash": closing_cash,
                "closed_at": fields.Datetime.now(),
                "state": "closed",
            }
        )
        return True
