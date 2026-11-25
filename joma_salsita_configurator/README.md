# joma_salsita_configurator (Odoo 16)

Integra el configurador JOMA Mail de Salsita en la web de Odoo y autentica a los
clientes conectados (portal e internos) con un JWT ES256 canjeado por un código
de un solo uso, según la guía de integración de Salsita.

- Página: `/configurador` (web «Joma», parámetro `joma_salsita.website_ids`)
- Autorización: `POST /api/configurator/authorization` (CSRF estándar de Odoo)
- Clave pública para Salsita (solo administradores): `/joma_salsita/public_jwk.json`
- Parámetros: Ajustes > Técnico > Parámetros del sistema, prefijo `joma_salsita.`
- Clave privada: parámetro `joma_salsita.private_key_pem` (generada al instalar)
  o fichero PEM indicado en odoo.conf con `joma_salsita_private_key_file`

Instrucciones completas de instalación en el documento que acompaña al módulo.
