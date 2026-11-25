# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def post_init_hook(cr, registry):
    """Genera el par de claves EC P-256 al instalar (solo si no existe)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["joma.salsita.auth"]._ensure_signing_key()
