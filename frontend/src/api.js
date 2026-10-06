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

// Al marcar avisos como leidos, el contador del menu se vuelve a consultar.
export const AVISOS_CAMBIARON = 'rrhh:avisos-cambiaron'

// archivo: true devuelve { blob, nombre } en lugar de JSON (exportaciones).
// datos: FormData para subir archivos (el navegador pone el Content-Type).
async function pedir(ruta, { metodo = 'GET', cuerpo, formulario, datos, archivo = false } = {}) {
  const encabezados = {}
  const token = leerToken()
  if (token) encabezados.Authorization = `Bearer ${token}`
  let body
  if (formulario) {
    body = new URLSearchParams(formulario)
  } else if (datos) {
    body = datos
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

  if (respuesta.ok && archivo) {
    const nombre = (respuesta.headers.get('Content-Disposition') ?? '').match(/filename="([^"]+)"/)?.[1]
    return { blob: await respuesta.blob(), nombre }
  }
  if (respuesta.status === 204) return null
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
  // Con MFA activo, login devuelve { mfa_requerido, mfa_token } en lugar del token
  verificarMfa: (mfaToken, codigo) =>
    pedir('/auth/mfa', { metodo: 'POST', cuerpo: { mfa_token: mfaToken, codigo } }),
  yo: () => pedir('/auth/yo'),
  // Devuelve un token nuevo: las demas sesiones de la persona se cierran
  cambiarContrasena: (actual, nueva) => pedir('/auth/contrasena', { metodo: 'POST', cuerpo: { actual, nueva } }),
  configurarMfa: () => pedir('/auth/mfa/configurar', { metodo: 'POST' }),
  activarMfa: (codigo) => pedir('/auth/mfa/activar', { metodo: 'POST', cuerpo: { codigo } }),
  // Cuentas: TI las administra; RRHH solo las consulta
  cuentas: () => pedir('/usuarios'),
  cambiosCuentas: () => pedir('/usuarios/cambios' + consulta({ limite: 100 })),
  crearCuenta: (datos) => pedir('/usuarios', { metodo: 'POST', cuerpo: datos }),
  modificarCuenta: (id, cambios) => pedir(`/usuarios/${id}`, { metodo: 'PATCH', cuerpo: cambios }),
  restablecerContrasena: (id) => pedir(`/usuarios/${id}/contrasena`, { metodo: 'POST' }),
  reiniciarMfa: (id) => pedir(`/usuarios/${id}/mfa/reiniciar`, { metodo: 'POST' }),
  // Modo demostracion: cuentas de prueba y el codigo que daria el telefono
  demo: () => pedir('/demo'),
  marca: () => pedir('/marca'),
  // Carga de datos de los sistemas fuente (solo RRHH)
  fuentesDeDatos: () => pedir('/cargas/fuentes'),
  cargas: () => pedir('/cargas'),
  subirArchivo: (fuente, archivo) => {
    const datos = new FormData()
    datos.append('archivo', archivo)
    return pedir(`/cargas/${encodeURIComponent(fuente)}`, { metodo: 'POST', datos })
  },
  aplicarCarga: (id) => pedir(`/cargas/${id}/aplicar`, { metodo: 'POST' }),
  descartarCarga: (id) => pedir(`/cargas/${id}/descartar`, { metodo: 'POST' }),
  plantilla: (fuente) => pedir(`/cargas/plantillas/${encodeURIComponent(fuente)}`, { archivo: true }),
  ejemploDeCarga: (fuente) => pedir(`/cargas/ejemplos/${encodeURIComponent(fuente)}`, { archivo: true }),
  codigoDemo: (mfaToken) => pedir('/demo/codigo', { metodo: 'POST', cuerpo: { mfa_token: mfaToken } }),
  codigoDemoConfiguracion: () => pedir('/demo/codigo-configuracion'),
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
  // Solo reportes aprobados; formato: 'pdf' o 'pptx'
  exportar: (id, formato) => pedir(`/narrativas/${id}/exportar` + consulta({ formato }), { archivo: true }),
  // Avisos (RF-09): { no_leidos, avisos }
  avisos: ({ soloNoLeidos, limite } = {}) =>
    pedir('/avisos' + consulta({ solo_no_leidos: soloNoLeidos, limite })),
  marcarAvisoLeido: (id) => pedir(`/avisos/${id}/leido`, { metodo: 'POST' }),
  marcarAvisosLeidos: () => pedir('/avisos/leidos', { metodo: 'POST' }),
  // Configuracion (RF-12): solo RRHH la cambia; la API responde 403 a los demas
  actualizarUmbral: (indicador, umbralAtencion, umbralCritico) =>
    pedir(`/umbrales/${encodeURIComponent(indicador)}`, {
      metodo: 'PUT',
      cuerpo: { umbral_atencion: umbralAtencion, umbral_critico: umbralCritico },
    }),
  cambiosUmbrales: () => pedir('/umbrales/cambios'),
  programacion: () => pedir('/programacion'),
  guardarProgramacion: (activa, diaDelMes) =>
    pedir('/programacion', { metodo: 'PUT', cuerpo: { activa, dia_del_mes: diaDelMes } }),
}
