# -*- coding: utf-8 -*-
"""Firma de JWT ES256 y canje por código de autorización de Salsita.

Flujo (guía JOMA Mail, sección 2):
  1. El backend firma un JWT ES256 (EC P-256) con el email verificado del
     cliente y sus datos opcionales.
  2. El backend envía {clientId, accessToken} al endpoint /environments/authorize
     y recibe un authorizationCode de un solo uso (caduca en 5 minutos).
  3. El navegador asigna configurator.authorizationCode antes de encenderlo.

La clave privada nunca sale del servidor.
"""
import base64
import json
import logging
import time

import requests

from odoo import api, models, tools
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import (
        decode_dss_signature,
    )
except ImportError:  # pragma: no cover
    _logger.error("joma_salsita_configurator necesita la librería 'cryptography'")

PARAM_PREFIX = "joma_salsita."
PARAM_PRIVATE_KEY = PARAM_PREFIX + "private_key_pem"
# Opción alternativa: ruta a un fichero PEM indicada en odoo.conf
CONF_PRIVATE_KEY_FILE = "joma_salsita_private_key_file"

DEFAULTS = {
    "client_id": "",
    "authorization_url": "https://production-eu-central-1.salsita.ai/environments/authorize",
    "script_url": "https://joma-mail.salsita.ai/salsita-embedded-configurator.js",
    "issuer": "joma-website",
    "audience": "joma-mail-configurator",
    "token_ttl": "10800",  # 3 horas, como en la guía
    "allowed_box_types": "mailbox,parcelbox",
    "website_ids": "",  # vacío = todas las webs
    "fallback_locale": "es",
    "request_timeout": "15",
}


class SalsitaAuthError(Exception):
    """Error al obtener el código de autorización de Salsita."""


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _json_b64url(value):
    return _b64url(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


class JomaSalsitaAuth(models.AbstractModel):
    _name = "joma.salsita.auth"
    _description = "Autenticación de clientes en el configurador Salsita"

    # ------------------------------------------------------------------
    # Parámetros
    # ------------------------------------------------------------------
    @api.model
    def _param(self, key):
        value = self.env["ir.config_parameter"].sudo().get_param(PARAM_PREFIX + key)
        if value in (None, False, ""):
            return DEFAULTS.get(key, "")
        return value.strip()

    @api.model
    def _allowed_box_types(self):
        raw = self._param("allowed_box_types")
        return [v.strip() for v in raw.split(",") if v.strip()]

    @api.model
    def _is_website_allowed(self, website):
        raw = self._param("website_ids")
        if not raw:
            return True
        try:
            ids = {int(v) for v in raw.split(",") if v.strip()}
        except ValueError:
            _logger.error("Parámetro %swebsite_ids no válido: %r", PARAM_PREFIX, raw)
            return False
        return bool(website) and website.id in ids

    # ------------------------------------------------------------------
    # Claves
    # ------------------------------------------------------------------
    @api.model
    def _ensure_signing_key(self):
        """Crea la clave privada EC P-256 si no hay ninguna configurada."""
        if tools.config.get(CONF_PRIVATE_KEY_FILE):
            return
        icp = self.env["ir.config_parameter"].sudo()
        if icp.get_param(PARAM_PRIVATE_KEY):
            return
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        icp.set_param(PARAM_PRIVATE_KEY, pem)
        _logger.info("joma_salsita_configurator: generada nueva clave de firma EC P-256")

    @api.model
    def _get_private_key(self):
        path = tools.config.get(CONF_PRIVATE_KEY_FILE)
        if path:
            with open(path, "rb") as fh:
                pem = fh.read()
        else:
            pem = self.env["ir.config_parameter"].sudo().get_param(PARAM_PRIVATE_KEY)
            if not pem:
                raise SalsitaAuthError("No hay clave de firma configurada")
            pem = pem.encode("ascii")
        key = serialization.load_pem_private_key(pem, password=None, backend=default_backend())
        if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
            raise SalsitaAuthError("La clave de firma debe ser EC P-256")
        return key

    @api.model
    def get_public_jwk(self):
        """JWK pública (sin el miembro privado 'd') para enviar a Salsita."""
        numbers = self._get_private_key().public_key().public_numbers()
        return {
            "kty": "EC",
            "crv": "P-256",
            "x": _b64url(numbers.x.to_bytes(32, "big")),
            "y": _b64url(numbers.y.to_bytes(32, "big")),
            "use": "sig",
            "alg": "ES256",
        }

    @api.model
    def action_regenerate_signing_key(self):
        """Rota la clave. Después hay que enviar la nueva JWK pública a Salsita:
        hasta que la configuren, los clientes entrarán como anónimos."""
        self.env["ir.config_parameter"].sudo().set_param(PARAM_PRIVATE_KEY, False)
        self._ensure_signing_key()
        return self.get_public_jwk()

    # ------------------------------------------------------------------
    # Claims
    # ------------------------------------------------------------------
    @api.model
    def _build_claims(self, user):
        """Claims del JWT a partir del usuario de Odoo (portal o interno).

        Devuelve None si el usuario no tiene un email válido (entrará como
        anónimo). Los opcionales vacíos se omiten, como exige Salsita.
        """
        user = user.sudo()
        partner = user.partner_id
        email = email_normalize(partner.email or "") or email_normalize(user.login or "")
        if not email:
            _logger.warning(
                "Configurador Salsita: el usuario %s (id %s) no tiene email válido; entra como anónimo",
                user.login, user.id,
            )
            return None

        commercial = partner.commercial_partner_id
        if partner.is_company:
            company_name = partner.name
        elif commercial and commercial != partner:
            company_name = commercial.name
        else:
            company_name = partner.company_name or (user.company_id.name if user.share is False else "")

        # Dirección: la del contacto; si no tiene calle, la de su empresa
        addr = partner if (partner.street or partner.city) else commercial

        now = int(time.time())
        claims = {
            "iss": self._param("issuer"),
            "aud": self._param("audience"),
            "iat": now,
            "exp": now + int(self._param("token_ttl") or 10800),
            "email": email,
            "sub": str(partner.id),
        }
        optional = {
            "name": partner.name,
            "company_name": company_name,
            "job_position": partner.function,
            "phone": partner.phone or partner.mobile or commercial.phone,
            "website": partner.website or commercial.website,
            "street": addr.street,
            "street2": addr.street2,
            "city": addr.city,
            "postal_code": addr.zip,
            "state": addr.state_id.name,
            "country": addr.country_id.code,
        }
        for key, value in optional.items():
            if isinstance(value, str) and value.strip():
                claims[key] = value.strip()
        return claims

    # ------------------------------------------------------------------
    # JWT y canje
    # ------------------------------------------------------------------
    @api.model
    def _sign_jwt(self, claims):
        header = {"alg": "ES256", "typ": "JWT"}
        unsigned = "%s.%s" % (_json_b64url(header), _json_b64url(claims))
        der = self._get_private_key().sign(unsigned.encode("ascii"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        # Formato JWS (IEEE P1363): r || s, 32 bytes cada uno
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return "%s.%s" % (unsigned, _b64url(signature))

    @api.model
    def get_authorization_code(self, user):
        """Devuelve un authorizationCode de un solo uso para el usuario, o
        None si no se puede identificar (sin email válido)."""
        claims = self._build_claims(user)
        if not claims:
            return None
        client_id = self._param("client_id")
        if not client_id:
            raise SalsitaAuthError("Falta el parámetro %sclient_id" % PARAM_PREFIX)
        token = self._sign_jwt(claims)
        try:
            response = requests.post(
                self._param("authorization_url"),
                json={"clientId": client_id, "accessToken": token},
                timeout=float(self._param("request_timeout") or 15),
            )
        except requests.RequestException as exc:
            raise SalsitaAuthError("Error de conexión con Salsita: %s" % exc) from exc
        if not response.ok:
            raise SalsitaAuthError(
                "Salsita rechazó la autorización (HTTP %s): %s"
                % (response.status_code, (response.text or "")[:500])
            )
        try:
            code = response.json().get("authorizationCode")
        except ValueError as exc:
            raise SalsitaAuthError("Respuesta de Salsita no es JSON") from exc
        if not code:
            raise SalsitaAuthError("La respuesta de Salsita no trae authorizationCode")
        return code
