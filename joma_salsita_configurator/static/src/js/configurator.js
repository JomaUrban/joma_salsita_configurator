// Inserción del configurador JOMA Mail (Salsita) en la web de Odoo.
// Sigue la guía de integración de Salsita (secciones 01, 02 y 04).
const CUSTOMER_PREFIX = 'joma-customer:configurator-'
const OWNER_KEY = 'joma-salsita:owner'

const host = document.getElementById('joma-salsita-configurator')
const errorBox = document.getElementById('joma-salsita-error')
const data = host ? host.dataset : null

function storages() {
  const list = []
  try { list.push(window.sessionStorage) } catch (e) { /* sin acceso */ }
  try { list.push(window.localStorage) } catch (e) { /* sin acceso */ }
  return list
}

// Borra la sesión de cliente guardada por el configurador (sección 04).
// Usa las claves exactas de la guía y, por si acaso, todas las del prefijo
// joma-customer: (no toca la sesión de admin ni las configuraciones guardadas).
function clearCustomerSession(bundle) {
  const keys = []
  const storageId = bundle?.config?.defaultEnvs?.deploymentId
  if (storageId) {
    keys.push(
      `joma-customer:configurator-session-token-configurator-${storageId}`,
      `joma-customer:configurator-session-token-admin-${storageId}`,
      `joma-customer:configurator-refresh-token-${storageId}`,
      `joma-customer:configurator-logged-out-${storageId}`,
    )
  }
  for (const storage of storages()) {
    const all = []
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i)
      if (key && key.startsWith(CUSTOMER_PREFIX)) all.push(key)
    }
    for (const key of new Set([...keys, ...all])) storage.removeItem(key)
  }
}

async function fetchAuthorizationCode() {
  const body = new URLSearchParams({ csrf_token: data.csrf })
  const response = await fetch(data.authUrl, {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    body,
  })
  if (!response.ok) throw new Error(`Autorización del configurador fallida (HTTP ${response.status})`)
  const { authorizationCode } = await response.json()
  return authorizationCode || null
}

async function main() {
  if (!host) return
  const { default: bundle } = await import(data.scriptUrl)

  // Si la sesión guardada es de otro usuario (o de un anónimo), se limpia.
  let previousOwner = null
  try { previousOwner = localStorage.getItem(OWNER_KEY) } catch (e) { /* */ }
  if (previousOwner !== data.owner) {
    clearCustomerSession(bundle)
    try { localStorage.setItem(OWNER_KEY, data.owner) } catch (e) { /* */ }
  }

  const tagName = bundle.mount() // una sola vez por bundle cargado
  await customElements.whenDefined(tagName)

  let instance = null
  let lastReauth = 0

  async function mountConfigurator() {
    if (instance) {
      instance.power = 'off'
      instance.remove()
      instance = null
    }
    const configurator = document.createElement(tagName)
    configurator.power = 'off'
    configurator.integrationMode = 'headless'
    configurator.locale = data.locale
    configurator.allowedBoxTypes = JSON.parse(data.boxTypes || '[]')
    configurator.style.display = 'block'
    configurator.style.height = '100%'
    configurator.route = { route: 'Index' }

    if (data.logged === '1') {
      try {
        const code = await fetchAuthorizationCode()
        if (code) configurator.authorizationCode = code
      } catch (error) {
        // Sin código el configurador funciona como anónimo (sin precios).
        console.error(error)
      }
    }

    // Sesión caducada o rechazada: pedir un código nuevo y volver a montar
    // (como máximo una vez por minuto para no entrar en bucle).
    configurator.addEventListener('authentication-failed', async () => {
      if (Date.now() - lastReauth < 60000) return
      lastReauth = Date.now()
      clearCustomerSession(bundle)
      await mountConfigurator()
    })

    host.append(configurator)
    configurator.power = 'on'
    instance = configurator
  }

  await mountConfigurator()
}

main().catch((error) => {
  console.error('Configurador JOMA Mail:', error)
  if (errorBox) errorBox.classList.remove('d-none')
})
