// Cliente de la API (FastAPI). Todas las llamadas pasan por pedir(): agrega el
// token de sesion y convierte los errores en mensajes para la persona usuaria.

export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

const LLAVE_TOKEN = 'rrhh.token'

// El token vive en sessionStorage: se borra al cerrar la pestana y caduca en
// el servidor (60 minutos por defecto). Nunca en localStorage.
export function leerToken() {
  try {
    return sessionStorage.getItem(LLAVE_TOKEN)
  } catch {
    return null
  }
}

export function guardarToken(token) {
  try {
    if (token) sessionStorage.setItem(LLAVE_TOKEN, token)
    else sessionStorage.removeItem(LLAVE_TOKEN)
  } catch {
    // sin almacenamiento la sesion dura hasta recargar la pagina
  }
}

export class ErrorDeApi extends Error {
  constructor(mensaje, estado) {
    super(mensaje)
    this.estado = estado // codigo HTTP; 0 si no hubo respuesta
  }
}

// Si la API responde 401 (token vencido o usuario desactivado), la sesion se
// cierra en toda la aplicacion (ver sesion.jsx).
export const SESION_VENCIDA = 'rrhh:sesion-vencida'

async function pedir(ruta, { metodo = 'GET', cuerpo, formulario } = {}) {
  const encabezados = {}
  const token = leerToken()
  if (token) encabezados.Authorization = `Bearer ${token}`
  let body
  if (formulario) {
    body = new URLSearchParams(formulario)
  } else if (cuerpo !== undefined) {
    encabezados['Content-Type'] = 'application/json'
    body = JSON.stringify(cuerpo)
  }

  let respuesta
  try {
    respuesta = await fetch(API_URL + ruta, { method: metodo, headers: encabezados, body })
  } catch {
    throw new ErrorDeApi(`No se pudo conectar con la API (${API_URL}). Revisa que esté encendida.`, 0)
  }

  if (respuesta.ok) return respuesta.json()

  let detalle = null
  try {
    detalle = (await respuesta.json()).detail
  } catch {
    // respuesta sin JSON
  }
  // FastAPI devuelve una lista cuando falla la validacion (422)
  const deValidacion = Array.isArray(detalle) ? detalle[0]?.msg?.replace(/^Value error, /, '') : null
  const mensaje = typeof detalle === 'string' ? detalle : deValidacion || `Error ${respuesta.status} de la API`
  if (respuesta.status === 401 && token) {
    window.dispatchEvent(new CustomEvent(SESION_VENCIDA, { detail: mensaje }))
  }
  throw new ErrorDeApi(mensaje, respuesta.status)
}

function consulta(parametros) {
  const limpios = Object.entries(parametros).filter(([, v]) => v !== undefined && v !== null && v !== '')
  return limpios.length ? '?' + new URLSearchParams(limpios) : ''
}

export const api = {
  login: (usuario, contrasena) =>
    pedir('/auth/login', { metodo: 'POST', formulario: { username: usuario, password: contrasena } }),
  yo: () => pedir('/auth/yo'),
  areas: () => pedir('/areas'),
  periodos: () => pedir('/periodos'),
  umbrales: () => pedir('/umbrales'),
  kpis: (periodo, areaId) => pedir('/kpis' + consulta({ periodo, area_id: areaId })),
  serie: (indicador, areaId) => pedir(`/kpis/serie/${encodeURIComponent(indicador)}` + consulta({ area_id: areaId })),
  solicitarNarrativa: (periodo, areaId) =>
    pedir('/narrativas', { metodo: 'POST', cuerpo: { periodo, area_id: areaId } }),
  narrativa: (id) => pedir(`/narrativas/${id}`),
  historial: ({ areaId, periodo, revision, limite = 50 } = {}) =>
    pedir('/narrativas' + consulta({ area_id: areaId, periodo, revision, limite })),
  revisar: (id, decision, comentario) =>
    pedir(`/narrativas/${id}/revision`, { metodo: 'POST', cuerpo: { decision, comentario } }),
}
