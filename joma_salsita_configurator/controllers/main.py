# -*- coding: utf-8 -*-
import json
import logging

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from ..models.salsita_auth import SalsitaAuthError

_logger = logging.getLogger(__name__)

NO_STORE = [("Cache-Control", "no-store"), ("Pragma", "no-cache")]


class JomaSalsitaConfigurator(http.Controller):

    def _auth(self):
        return request.env["joma.salsita.auth"].sudo()

    def _check_website(self):
        if not self._auth()._is_website_allowed(request.website):
            raise NotFound()

    @http.route("/configurador", type="http", auth="public", website=True, sitemap=True)
    def configurator_page(self, **kw):
        self._check_website()
        auth = self._auth()
        user = request.env.user
        is_logged = not user._is_public()
        lang = (request.lang.code or "")[:2] if request.lang else ""
        locale = lang if lang in ("es", "en") else auth._param("fallback_locale")
        values = {
            "salsita_script_url": auth._param("script_url"),
            "salsita_locale": locale,
            "salsita_box_types": json.dumps(auth._allowed_box_types()),
            "salsita_logged": "1" if is_logged else "0",
            # Identifica al dueño de la sesión guardada del configurador para
            # limpiarla si cambia el usuario (logout / cambio de cuenta).
            "salsita_owner": "u%s" % user.id if is_logged else "public",
        }
        return request.render("joma_salsita_configurator.configurator_page", values)

    @http.route(
        "/api/configurator/authorization",
        type="http", auth="public", methods=["POST"], website=True, sitemap=False,
        # csrf=True (por defecto): el navegador envía csrf_token en el cuerpo
    )
    def configurator_authorization(self, **kw):
        self._check_website()
        user = request.env.user
        if user._is_public():
            return request.make_json_response({"authorizationCode": None}, headers=NO_STORE)
        try:
            code = self._auth().get_authorization_code(user)
        except SalsitaAuthError as exc:
            _logger.error("Configurador Salsita, usuario %s: %s", user.login, exc)
            return request.make_json_response(
                {"error": "authorization_failed"}, headers=NO_STORE, status=502
            )
        return request.make_json_response({"authorizationCode": code}, headers=NO_STORE)

    @http.route("/joma_salsita/public_jwk.json", type="http", auth="user", sitemap=False)
    def public_jwk(self, **kw):
        if not request.env.user.has_group("base.group_system"):
            raise NotFound()
        return request.make_json_response(self._auth().get_public_jwk(), headers=NO_STORE)
