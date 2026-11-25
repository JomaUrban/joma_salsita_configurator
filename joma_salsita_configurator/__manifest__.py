# -*- coding: utf-8 -*-
{
    "name": "JOMA - Configurador Salsita (JOMA Mail)",
    "summary": "Inserta el configurador JOMA Mail de Salsita en la web y "
               "autentica a los clientes de Odoo con JWT ES256",
    "version": "16.0.1.0.0",
    "category": "Website",
    "author": "JOMA (Jose María Gallastegui y Cía. S.A.)",
    "license": "LGPL-3",
    "depends": ["website", "portal"],
    "external_dependencies": {"python": ["cryptography", "requests"]},
    "data": [
        "data/ir_config_parameter.xml",
        "views/templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "joma_salsita_configurator/static/src/js/logout_cleanup.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
