import re
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from werkzeug.security import check_password_hash, generate_password_hash


class StorePosUser(models.Model):
    _name = "five.five.store.pos.user"
    _description = "Store POS User"
    _rec_name = "username"

    store_id = fields.Many2one(
        "five.five.store",
        string="Store",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(string="Display Name", required=True)
    username = fields.Char(string="Username", required=True, index=True)
    password = fields.Char(string="Password Hash", copy=False)
    password_plain = fields.Char(
        string="Password",
        compute="_compute_password_plain",
        inverse="_inverse_password_plain",
        store=False,
    )
    access_token = fields.Char(string="Access Token", copy=False)
    active = fields.Boolean(default=True)
    tab_pos = fields.Boolean(string="เข้าสู่การขาย", default=True)
    tab_requisition = fields.Boolean(string="เบิกสินค้า", default=True)
    tab_requisition_history = fields.Boolean(string="ประวัติการเบิก", default=True)
    tab_stock = fields.Boolean(string="สต็อกสินค้า", default=True)
    tab_sales = fields.Boolean(string="ประวัติการขาย", default=True)
    tab_close_session = fields.Boolean(string="ปิดกะ", default=True)

    _sql_constraints = [
        (
            "five_five_store_pos_user_username_uniq",
            "unique(username)",
            "Username must be unique.",
        ),
    ]

    @api.depends("password")
    def _compute_password_plain(self):
        for user in self:
            user.password_plain = False

    def _inverse_password_plain(self):
        for user in self:
            if user.password_plain:
                if len(user.password_plain) < 4:
                    raise ValidationError(_("Password must be at least 4 characters."))
                user.password = self._hash_password(user.password_plain)

    @api.model
    def _hash_password(self, plain_password):
        return generate_password_hash(plain_password)

    def _check_password(self, plain_password):
        self.ensure_one()
        if not self.password:
            return False
        return check_password_hash(self.password, plain_password)

    def get_tab_permissions(self):
        self.ensure_one()
        return {
            "pos": self.tab_pos,
            "requisition": self.tab_requisition,
            "requisition_history": self.tab_requisition_history,
            "stock": self.tab_stock,
            "sales": self.tab_sales,
            "close_session": self.tab_close_session,
        }

    def check_tab_access(self, tab_key):
        self.ensure_one()
        permissions = self.get_tab_permissions()
        if tab_key not in permissions:
            raise UserError(_("Unknown tab: %s") % tab_key)
        if not permissions[tab_key]:
            raise UserError(_("You do not have access to this feature."))

    @api.constrains(
        "tab_pos",
        "tab_requisition",
        "tab_requisition_history",
        "tab_stock",
        "tab_sales",
        "tab_close_session",
    )
    def _check_at_least_one_tab(self):
        tab_fields = (
            "tab_pos",
            "tab_requisition",
            "tab_requisition_history",
            "tab_stock",
            "tab_sales",
            "tab_close_session",
        )
        for user in self:
            if not any(user[field] for field in tab_fields):
                raise ValidationError(_("Please enable at least one menu tab."))

    def _generate_username(self):
        self.ensure_one()
        return self._generate_username_for_store(self.store_id)

    @api.model
    def _generate_username_for_store(self, store):
        store_slug = re.sub(r"[^a-z0-9]+", "", (store.name or "store").lower())[:12] or "store"
        for _ in range(200):
            candidate = f"{store_slug}{secrets.randbelow(9000) + 1000}"
            if not self.search_count([("username", "=", candidate)]):
                return candidate
        raise UserError(_("Unable to generate a unique username. Please try again."))

    def _prepare_password_from_vals(self, vals):
        plain = vals.pop("password_plain", None)
        if plain:
            if len(plain) < 4:
                raise ValidationError(_("Password must be at least 4 characters."))
            vals["password"] = self._hash_password(plain)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            vals = self._prepare_password_from_vals(vals)
            if not vals.get("password"):
                raise ValidationError(_("Please set a password for the POS user."))
            if not vals.get("username"):
                store = self.env["five.five.store"].browse(vals["store_id"])
                vals["username"] = self._generate_username_for_store(store)
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        vals = dict(vals)
        plain = vals.pop("password_plain", None)
        if plain:
            if len(plain) < 4:
                raise ValidationError(_("Password must be at least 4 characters."))
            vals["password"] = self._hash_password(plain)
        return super().write(vals)

    def action_generate_password(self):
        self.ensure_one()
        password = secrets.token_urlsafe(8)
        return {
            "type": "ir.actions.act_window",
            "name": _("Generated Password"),
            "res_model": "five.five.store.pos.user.credential.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_pos_user_id": self.id,
                "default_username": self.username,
                "default_password": password,
                "default_is_suggestion": True,
            },
        }

    def action_change_password(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Change Password"),
            "res_model": "five.five.store.pos.user.change.password.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_pos_user_id": self.id,
            },
        }

    @api.model
    def authenticate(self, username, password):
        user = self.sudo().search(
            [("username", "=", username), ("active", "=", True)],
            limit=1,
        )
        if not user or not user._check_password(password):
            return False
        token = secrets.token_urlsafe(32)
        user.write({"access_token": token})
        return user, token

    @api.model
    def get_user_from_token(self, token):
        if not token:
            return self.browse()
        return self.sudo().search(
            [("access_token", "=", token), ("active", "=", True)],
            limit=1,
        )

    def action_logout_token(self):
        self.write({"access_token": False})


class StorePosUserCredentialWizard(models.TransientModel):
    _name = "five.five.store.pos.user.credential.wizard"
    _description = "Show generated POS credentials"

    pos_user_id = fields.Many2one("five.five.store.pos.user", required=True)
    username = fields.Char(string="Username", readonly=True)
    password = fields.Char(string="Password", readonly=True)
    is_suggestion = fields.Boolean(default=False)

    def action_apply_password(self):
        self.ensure_one()
        if not self.password:
            raise UserError(_("No password to apply."))
        self.pos_user_id.write({"password_plain": self.password})
        return {"type": "ir.actions.act_window_close"}


class StorePosUserChangePasswordWizard(models.TransientModel):
    _name = "five.five.store.pos.user.change.password.wizard"
    _description = "Change POS user password"

    pos_user_id = fields.Many2one("five.five.store.pos.user", required=True)
    new_password = fields.Char(string="New Password", required=True)
    confirm_password = fields.Char(string="Confirm Password", required=True)

    def action_change_password(self):
        self.ensure_one()
        if self.new_password != self.confirm_password:
            raise ValidationError(_("Passwords do not match."))
        if len(self.new_password) < 4:
            raise ValidationError(_("Password must be at least 4 characters."))
        self.pos_user_id.write({"password_plain": self.new_password})
        return {"type": "ir.actions.act_window_close"}
