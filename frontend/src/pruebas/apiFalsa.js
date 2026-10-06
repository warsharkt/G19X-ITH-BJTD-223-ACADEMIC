// API simulada para las pruebas: reemplaza fetch y responde como FastAPI.
import { vi } from 'vitest'

export const USUARIOS = {
  ana: { id: 1, usuario: 'ana', nombre: 'Ana López', rol: 'rrhh', area_id: null, areas_permitidas: [0, 1, 2] },
  eva: { id: 4, usuario: 'eva', nombre: 'Eva Ruiz', rol: 'rrhh', area_id: null, areas_permitidas: [0, 1, 2] },
  dir: { id: 2, usuario: 'dir', nombre: 'Dirección General', rol: 'direccion', area_id: null, areas_permitidas: [0] },
  ti: { id: 3, usuario: 'ti', nombre: 'Soporte TI', rol: 'admin_ti', area_id: null, areas_permitidas: [0, 1, 2] },
  // con contrasena temporal: debe cambiarla antes de usar el sistema
  nuevo: { id: 5, usuario: 'nuevo', nombre: 'Nuevo Director', rol: 'direccion', area_id: null, areas_permitidas: [0], pendiente: 'cambiar_contrasena' },
  // con MFA activo: el inicio de sesion pide el codigo
  lia: { id: 6, usuario: 'lia', nombre: 'Lía Torres', rol: 'rrhh', area_id: null, areas_permitidas: [0, 1, 2], mfa_activo: true, mfa_obligatorio: true, codigos_respaldo_restantes: 10 },
  // su rol exige MFA y aun no lo configura
  sinmfa: { id: 7, usuario: 'sinmfa', nombre: 'Raúl Díaz', rol: 'rrhh', area_id: null, areas_permitidas: [0, 1, 2], pendiente: 'configurar_mfa', mfa_obligatorio: true },
}
export const CODIGO_MFA = '123456'
const CODIGO_RESPALDO = 'abcde-fghij'
const CONTRASENA = 'contrasena-correcta'
const AREAS = [
  { id: 0, nombre: 'Corporativo' },
  { id: 1, nombre: 'Ventas' },
  { id: 2, nombre: 'Legal' },
]
const PERIODOS = ['2026-06', '2026-07', '2026-08']

const UMBRALES = [
  { indicador: 'rotacion_total', nombre: 'Tasa de rotación mensual', unidad: '%', sentido: 'mayor_es_peor', umbral_atencion: 2, umbral_critico: 3.5 },
  { indicador: 'enps', nombre: 'eNPS', unidad: 'puntos', sentido: 'menor_es_peor', umbral_atencion: 10, umbral_critico: 0 },
  { indicador: 'tasa_finalizacion', nombre: 'Tasa de finalización de cursos', unidad: '%', sentido: 'menor_es_peor', umbral_atencion: 80, umbral_critico: 72 },
]

function kpi(indicador, area_id, valor, estado, extra = {}) {
  const u = UMBRALES.find((x) => x.indicador === indicador)
  return {
    indicador, nombre: u.nombre, unidad: u.unidad, area_id, area: AREAS.find((a) => a.id === area_id).nombre,
    periodo: '2026-08-01', valor, n: 120, suprimido: false, var_mes_ant: 0.5, var_mes_ant_pct: 20,
    var_anio_ant: -0.2, var_anio_ant_pct: -5, estado, sentido: u.sentido,
    umbral_atencion: u.umbral_atencion, umbral_critico: u.umbral_critico, ...extra,
  }
}

const KPIS = {
  0: [kpi('rotacion_total', 0, 3.9, 'rojo'), kpi('enps', 0, 18, 'verde'), kpi('tasa_finalizacion', 0, 85, 'verde')],
  1: [kpi('rotacion_total', 1, 1.2, 'verde'), kpi('enps', 1, 6, 'amarillo'), kpi('tasa_finalizacion', 1, 90, 'verde')],
  2: [
    kpi('rotacion_total', 2, null, 'suprimido', { suprimido: true, n: 4 }),
    kpi('enps', 2, null, 'suprimido', { suprimido: true, n: 4 }),
    kpi('tasa_finalizacion', 2, 0, 'muestra_insuficiente', { n: 1 }),
  ],
}

const HECHO = {
  id: 'H01', indicador: 'rotacion_total', nombre: 'Tasa de rotación mensual', unidad: '%', area: 'Corporativo',
  periodo: '2026-08', valor: 3.9, valor_texto: '3.9 %', var_mes_ant: 0.5, var_mes_ant_texto: '+0.5 pts',
  var_anio_ant: null, var_anio_ant_texto: null, estado: 'rojo', n: 363, personas_texto: null,
  umbral_atencion: 2, umbral_atencion_texto: '2.0 %', umbral_critico: 3.5, umbral_critico_texto: '3.5 %',
  sentido: 'valores más altos son peores', evolucion_mes_ant: 'empeoró', evolucion_anio_ant: null,
  en_vigilancia: false, motivo_vigilancia: null, situacion: 'cruzó el umbral crítico', accion_base: 'Revisar bajas',
  confianza: 'alta', motivo_confianza: 'muestra e historia suficientes', fuente: 'HRIS (empleados)',
}

export const NARRATIVA = {
  periodo: '2026-08', area_id: 0, area: 'Corporativo', proveedor: 'ollama', modelo: 'qwen3:8b',
  version_prompt: 'v5', generado_en: '2026-10-03T18:00:00Z', requiere_revision: true, mes_estable: false,
  indicadores_sin_evaluar: [], intentos: 1,
  resumen: 'En agosto de 2026 el Corporativo tiene 1 indicador en rojo: la rotación mensual (3.9 %).',
  hallazgos: [{ titulo: 'Rotación al alza', texto: 'La rotación mensual empeoró y llegó a 3.9 %.', hechos: ['H01'], confianza: 'alta', fuentes: ['HRIS (empleados)'] }],
  recomendaciones: [{ accion: 'Revisar las bajas del mes por área.', hechos: ['H01'], confianza: 'alta', fuentes: ['HRIS (empleados)'] }],
  conteo_estados: { rojo: 1, amarillo: 0, verde: 2, por_vigilar: 0, total: 3 },
  hechos: [HECHO], advertencias: [],
}

// Revisiones hechas durante la prueba: id -> campos de revision
let revisiones = {}

function trabajo(id, estado, extra = {}) {
  return {
    id, area_id: 0, periodo: '2026-08', estado, solicitada_en: '2026-10-03T17:55:00Z',
    terminada_en: estado === 'en_proceso' ? null : '2026-10-03T18:00:00Z', proveedor: 'ollama',
    modelo: 'qwen3:8b', version_prompt: 'v5', rondas: 1, error: null, detalle_error: null,
    solicitada_por: 'ana', revision: 'pendiente', revisada_por: null, revisada_en: null,
    comentario_revision: null, narrativa: estado === 'lista' ? NARRATIVA : null, ...extra, ...revisiones[id],
  }
}

// Mismas reglas que POST /narrativas/{id}/revision de la API real
function revisar(usuario, id, { decision, comentario }) {
  const actual = trabajo(id, 'lista')
  if (usuario.rol !== 'rrhh') return respuesta(403, { detail: 'Solo Recursos Humanos puede aprobar o rechazar reportes' })
  const motivo = (comentario ?? '').trim()
  if (decision === 'rechazada' && motivo.length < 10)
    return respuesta(422, { detail: [{ msg: 'Value error, Al rechazar, explica el motivo en el comentario (mínimo 10 caracteres)' }] })
  if (actual.revision !== 'pendiente') return respuesta(409, { detail: `Esta narrativa ya fue ${actual.revision}` })
  if (actual.solicitada_por === usuario.usuario)
    return respuesta(403, { detail: 'No puedes revisar una narrativa que tú solicitaste: debe hacerlo otra persona de RRHH' })
  revisiones[id] = { revision: decision, revisada_por: usuario.usuario, revisada_en: '2026-10-04T10:00:00Z', comentario_revision: motivo || null }
  return respuesta(200, trabajo(id, 'lista'))
}

// Exportacion: igual que la API real, solo reportes aprobados
function exportar(id, formato, estado) {
  const actual = trabajo(id, 'lista')
  if (actual.revision !== 'aprobada')
    return respuesta(409, { detail: `Solo se pueden exportar reportes aprobados por RRHH; este está ${actual.revision}` })
  estado.exportaciones.push({ id, formato })
  const nombre = `reporte-rrhh-corporativo-2026-08.${formato}`
  return Promise.resolve(
    new Response(new Blob([formato === 'pdf' ? '%PDF-1.4' : 'PK']), {
      status: 200,
      headers: { 'Content-Type': 'application/octet-stream', 'Content-Disposition': `attachment; filename="${nombre}"` },
    }),
  )
}

// Avisos de cada persona al empezar la prueba (como los genera la API)
function avisosIniciales() {
  return {
    ana: [
      { id: 12, tipo: 'revision', area_id: 0, titulo: 'Reporte de Corporativo, agosto 2026 listo para revisión', enlace: '/narrativas/5', creado_en: '2026-10-03T18:00:00Z', leido_en: null },
      { id: 11, tipo: 'alerta', area_id: 0, titulo: 'Corporativo, agosto 2026: 1 indicador en rojo (Tasa de rotación mensual)', enlace: '/tablero?area=0&periodo=2026-08', creado_en: '2026-10-03T07:00:00Z', leido_en: null },
      { id: 10, tipo: 'aprobado', area_id: 1, titulo: 'Reporte de Ventas, julio 2026 aprobado: ya se puede descargar', enlace: '/narrativas/4', creado_en: '2026-09-05T10:00:00Z', leido_en: '2026-09-05T11:00:00Z' },
    ],
    dir: [],
    eva: [],
    ti: [],
    nuevo: [],
    lia: [],
    sinmfa: [],
  }
}

// Mismas reglas que PUT /umbrales/{indicador} de la API real
function actualizarUmbral(usuario, indicador, { umbral_atencion, umbral_critico }, estado) {
  if (usuario.rol !== 'rrhh') return respuesta(403, { detail: 'Solo Recursos Humanos puede cambiar esta configuración' })
  const u = estado.umbrales.find((x) => x.indicador === indicador)
  if (!u) return respuesta(404, { detail: `El indicador '${indicador}' no existe` })
  if (u.sentido === 'mayor_es_peor' && umbral_critico < umbral_atencion)
    return respuesta(422, { detail: `En ${u.nombre} un valor más alto es peor: el umbral crítico debe ser mayor o igual que el de atención` })
  estado.cambios.unshift({
    id: estado.cambios.length + 1, indicador, nombre: u.nombre, unidad: u.unidad,
    atencion_antes: u.umbral_atencion, critico_antes: u.umbral_critico,
    atencion_nuevo: umbral_atencion, critico_nuevo: umbral_critico, usuario: usuario.usuario, cambiado_en: '2026-10-06T12:00:00Z',
  })
  Object.assign(u, { umbral_atencion, umbral_critico })
  return respuesta(200, u)
}

// Cuentas como las devuelve GET /usuarios
function cuentasIniciales() {
  return Object.values(USUARIOS).map((u) => ({
    id: u.id, usuario: u.usuario, nombre: u.nombre, rol: u.rol, area_id: u.area_id, correo: null, activo: true,
    bloqueado: false, debe_cambiar_contrasena: u.pendiente === 'cambiar_contrasena', mfa_activo: Boolean(u.mfa_activo),
    creado_en: '2026-09-01T10:00:00Z', ultimo_acceso: null,
  }))
}

// Mismas reglas que /usuarios de la API real: solo TI administra; RRHH consulta
function cuentas(usuario, pathname, metodo, cuerpo, estado) {
  const soloTi = () => respuesta(403, { detail: 'Solo Administración de TI puede administrar cuentas' })
  const anotar = (cuenta, accion, detalle = {}) =>
    estado.bitacora.unshift({ id: estado.bitacora.length + 1, usuario: cuenta, accion, detalle, hecho_por: usuario.usuario, hecho_en: '2026-10-06T12:00:00Z' })
  if (metodo === 'GET') {
    if (!['admin_ti', 'rrhh'].includes(usuario.rol)) return respuesta(403, { detail: 'Solo TI y Recursos Humanos pueden ver las cuentas' })
    return respuesta(200, pathname === '/usuarios/cambios' ? estado.bitacora : estado.cuentas)
  }
  if (usuario.rol !== 'admin_ti') return soloTi()
  if (pathname === '/usuarios' && metodo === 'POST') {
    if (estado.cuentas.some((c) => c.usuario === cuerpo.usuario)) return respuesta(422, { detail: `El usuario '${cuerpo.usuario}' ya existe` })
    const cuenta = { ...cuerpo, id: 100 + estado.cuentas.length, activo: true, bloqueado: false, debe_cambiar_contrasena: true, mfa_activo: false, creado_en: '2026-10-06T12:00:00Z', ultimo_acceso: null }
    estado.cuentas.push(cuenta)
    anotar(cuenta.usuario, 'crear', { nombre: cuenta.nombre, rol: cuenta.rol, area_id: cuenta.area_id, correo: cuenta.correo })
    return respuesta(201, { cuenta, contrasena_temporal: 'Tmp7-Kq3x-Pa9t' })
  }
  const [, , id, que] = pathname.split('/')
  const cuenta = estado.cuentas.find((c) => c.id === Number(id))
  if (!cuenta) return respuesta(404, { detail: `El usuario ${id} no existe` })
  if (metodo === 'PATCH') {
    const diferencias = Object.fromEntries(Object.entries(cuerpo).filter(([k, v]) => cuenta[k] !== v).map(([k, v]) => [k, [cuenta[k], v]]))
    Object.assign(cuenta, cuerpo)
    if (Object.keys(diferencias).length) anotar(cuenta.usuario, 'activo' in cuerpo ? (cuerpo.activo ? 'reactivar' : 'desactivar') : 'modificar', diferencias)
    return respuesta(200, cuenta)
  }
  if (que === 'contrasena') {
    Object.assign(cuenta, { debe_cambiar_contrasena: true, bloqueado: false })
    anotar(cuenta.usuario, 'restablecer_contrasena')
    return respuesta(200, { contrasena_temporal: 'Nva2-Rst8-Xm4p' })
  }
  cuenta.mfa_activo = false
  anotar(cuenta.usuario, 'reiniciar_mfa')
  return respuesta(200, cuenta)
}

function respuesta(estado, cuerpo) {
  return Promise.resolve(new Response(JSON.stringify(cuerpo), { status: estado, headers: { 'Content-Type': 'application/json' } }))
}

// Instala la API falsa. `opciones.consultasHastaLista`: cuantas veces se
// consulta la narrativa nueva antes de que pase de en_proceso a lista.
export function instalarApiFalsa({ consultasHastaLista = 1, fallaNarrativa = false } = {}) {
  const estado = {
    tokenValido: null, consultas: 0, solicitudes: [], exportaciones: [],
    pendientes: Object.fromEntries(Object.values(USUARIOS).map((u) => [u.usuario, u.pendiente ?? null])),
    contrasenasCambiadas: [],
    cuentas: cuentasIniciales(),
    bitacora: [],
    avisos: avisosIniciales(),
    umbrales: UMBRALES.map((u) => ({ ...u })),
    cambios: [],
    programacion: {
      activa: false, dia_del_mes: 5, modificada_por: null, modificada_en: null, correo_activo: false,
      corridas: [{ periodo: '2026-07', iniciada_en: '2026-08-05T07:00:00Z', origen: 'api', narrativas: 7 }],
    },
  }
  revisiones = {}
  const tokens = Object.fromEntries(Object.keys(USUARIOS).map((u) => [`token-${u}`, USUARIOS[u]]))

  const fetchFalso = vi.fn(async (url, opciones = {}) => {
    const { pathname, searchParams } = new URL(url)
    const metodo = opciones.method ?? 'GET'

    if (pathname === '/auth/login') {
      const f = new URLSearchParams(opciones.body)
      const quien = USUARIOS[f.get('username')]
      if (!quien || f.get('password') !== CONTRASENA) return respuesta(401, { detail: 'Usuario o contraseña incorrectos' })
      if (quien.mfa_activo)
        return respuesta(200, { access_token: null, mfa_requerido: true, mfa_token: `mfa-${quien.usuario}`, token_type: 'bearer', expira_en_minutos: 5 })
      return respuesta(200, { access_token: `token-${quien.usuario}`, mfa_requerido: false, token_type: 'bearer', expira_en_minutos: 60 })
    }
    if (pathname === '/auth/mfa') {
      const { mfa_token, codigo } = JSON.parse(opciones.body)
      const quien = USUARIOS[mfa_token.replace('mfa-', '')]
      if (!quien) return respuesta(401, { detail: 'La verificación venció; vuelve a escribir tu usuario y contraseña' })
      if (codigo !== CODIGO_MFA && codigo !== CODIGO_RESPALDO) return respuesta(401, { detail: 'El código no es correcto' })
      return respuesta(200, { access_token: `token-${quien.usuario}`, mfa_requerido: false, token_type: 'bearer', expira_en_minutos: 60 })
    }

    const usuario = tokens[(opciones.headers?.Authorization ?? '').replace('Bearer ', '')]
    if (!usuario || estado.tokenValido === false)
      return respuesta(401, { detail: 'Sesión no válida o vencida; vuelve a iniciar sesión' })
    const conDatos = usuario.rol !== 'admin_ti'
    const sinPermiso = () => respuesta(403, { detail: 'Tu rol no tiene acceso a datos de colaboradores' })

    const pendiente = estado.pendientes[usuario.usuario]
    if (pathname === '/auth/yo') return respuesta(200, { mfa_activo: false, mfa_obligatorio: false, codigos_respaldo_restantes: 0, ...usuario, pendiente })
    if (pathname === '/auth/contrasena') {
      const { actual, nueva } = JSON.parse(opciones.body)
      if (actual !== CONTRASENA) return respuesta(422, { detail: 'La contraseña actual no es correcta' })
      estado.contrasenasCambiadas.push({ usuario: usuario.usuario, nueva })
      if (pendiente === 'cambiar_contrasena') estado.pendientes[usuario.usuario] = null
      return respuesta(200, { access_token: `token-${usuario.usuario}`, token_type: 'bearer', expira_en_minutos: 60 })
    }
    if (pathname === '/auth/mfa/configurar')
      return respuesta(200, { secreto: 'JBSWY3DPEHPK3PXP', uri: 'otpauth://totp/Motor%20RRHH:sinmfa', qr: 'data:image/svg+xml;base64,PHN2Zy8+' })
    if (pathname === '/auth/mfa/activar') {
      if (JSON.parse(opciones.body).codigo !== CODIGO_MFA) return respuesta(422, { detail: 'El código no es correcto. Revisa que la hora de tu teléfono sea la correcta' })
      if (pendiente === 'configurar_mfa') estado.pendientes[usuario.usuario] = null
      return respuesta(200, { codigos: Array.from({ length: 10 }, (_, i) => `cod${i}a-bcdef`) })
    }
    if (pendiente) return respuesta(403, { detail: 'Antes de continuar resuelve lo pendiente' })
    if (pathname.startsWith('/usuarios')) return cuentas(usuario, pathname, metodo, opciones.body && JSON.parse(opciones.body), estado)
    if (pathname === '/areas') return respuesta(200, AREAS.filter((a) => usuario.areas_permitidas.includes(a.id)))
    if (pathname === '/periodos') return respuesta(200, PERIODOS)
    if (pathname === '/umbrales') return respuesta(200, estado.umbrales)
    if (pathname === '/umbrales/cambios') return respuesta(200, estado.cambios)
    const enUmbral = pathname.match(/^\/umbrales\/(\w+)$/)
    if (enUmbral && metodo === 'PUT') return actualizarUmbral(usuario, enUmbral[1], JSON.parse(opciones.body), estado)
    if (pathname === '/programacion' && metodo === 'PUT') {
      if (usuario.rol !== 'rrhh') return respuesta(403, { detail: 'Solo Recursos Humanos puede cambiar esta configuración' })
      const { activa, dia_del_mes } = JSON.parse(opciones.body)
      Object.assign(estado.programacion, { activa, dia_del_mes, modificada_por: usuario.usuario, modificada_en: '2026-10-06T12:00:00Z' })
      return respuesta(200, estado.programacion)
    }
    if (pathname === '/programacion') return respuesta(200, estado.programacion)

    const propios = estado.avisos[usuario.usuario]
    if (pathname === '/avisos') {
      const lista = searchParams.get('solo_no_leidos') === 'true' ? propios.filter((a) => !a.leido_en) : propios
      return respuesta(200, { no_leidos: propios.filter((a) => !a.leido_en).length, avisos: lista })
    }
    const enAviso = pathname.match(/^\/avisos\/(\d+)\/leido$/)
    if (enAviso && metodo === 'POST') {
      const aviso = propios.find((a) => a.id === Number(enAviso[1]))
      if (!aviso) return respuesta(404, { detail: 'El aviso no existe' })
      aviso.leido_en ??= '2026-10-06T12:00:00Z'
      return Promise.resolve(new Response(null, { status: 204 }))
    }
    if (pathname === '/avisos/leidos' && metodo === 'POST') {
      const pendientes = propios.filter((a) => !a.leido_en)
      pendientes.forEach((a) => (a.leido_en = '2026-10-06T12:00:00Z'))
      return respuesta(200, { marcados: pendientes.length })
    }
    if (!conDatos) return sinPermiso()

    if (pathname === '/kpis') return respuesta(200, KPIS[Number(searchParams.get('area_id') ?? 0)])
    if (pathname.startsWith('/kpis/serie/')) {
      const indicador = pathname.split('/').at(-1)
      const area = Number(searchParams.get('area_id') ?? 0)
      const actual = KPIS[area].find((k) => k.indicador === indicador)
      return respuesta(200, PERIODOS.map((p, i) => ({
        periodo: `${p}-01`, valor: actual.valor === null ? null : actual.valor - (2 - i) * 0.3, n: actual.n,
        suprimido: actual.suprimido, estado: actual.estado,
      })))
    }
    if (pathname === '/narrativas' && metodo === 'POST') {
      estado.solicitudes.push(JSON.parse(opciones.body))
      return respuesta(202, trabajo(7, 'en_proceso'))
    }
    const enRevision = pathname.match(/^\/narrativas\/(\d+)\/revision$/)
    if (enRevision && metodo === 'POST') return revisar(usuario, Number(enRevision[1]), JSON.parse(opciones.body))
    const enExportar = pathname.match(/^\/narrativas\/(\d+)\/exportar$/)
    if (enExportar) return exportar(Number(enExportar[1]), searchParams.get('formato'), estado)
    if (pathname === '/narrativas/5') return respuesta(200, trabajo(5, 'lista'))
    if (pathname === '/narrativas/7') {
      estado.consultas += 1
      if (estado.consultas <= consultasHastaLista) return respuesta(200, trabajo(7, 'en_proceso'))
      if (fallaNarrativa)
        return respuesta(200, trabajo(7, 'error', { error: 'El modelo no pasó los guardarrailes', detalle_error: ['Cifra 4.2 no está en los hechos'] }))
      return respuesta(200, trabajo(7, 'lista'))
    }
    if (pathname === '/narrativas') return respuesta(200, [trabajo(5, 'lista'), trabajo(6, 'error', { area_id: 1, error: 'Ollama no respondió' })])
    return respuesta(404, { detail: 'No existe' })
  })

  vi.stubGlobal('fetch', fetchFalso)
  return { fetch: fetchFalso, estado, contrasena: CONTRASENA }
}
