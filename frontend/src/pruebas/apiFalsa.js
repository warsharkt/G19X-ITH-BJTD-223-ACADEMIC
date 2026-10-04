// API simulada para las pruebas: reemplaza fetch y responde como FastAPI.
import { vi } from 'vitest'

export const USUARIOS = {
  ana: { id: 1, usuario: 'ana', nombre: 'Ana López', rol: 'rrhh', area_id: null, areas_permitidas: [0, 1, 2] },
  eva: { id: 4, usuario: 'eva', nombre: 'Eva Ruiz', rol: 'rrhh', area_id: null, areas_permitidas: [0, 1, 2] },
  dir: { id: 2, usuario: 'dir', nombre: 'Dirección General', rol: 'direccion', area_id: null, areas_permitidas: [0] },
  ti: { id: 3, usuario: 'ti', nombre: 'Soporte TI', rol: 'admin_ti', area_id: null, areas_permitidas: [0, 1, 2] },
}
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

function respuesta(estado, cuerpo) {
  return Promise.resolve(new Response(JSON.stringify(cuerpo), { status: estado, headers: { 'Content-Type': 'application/json' } }))
}

// Instala la API falsa. `opciones.consultasHastaLista`: cuantas veces se
// consulta la narrativa nueva antes de que pase de en_proceso a lista.
export function instalarApiFalsa({ consultasHastaLista = 1, fallaNarrativa = false } = {}) {
  const estado = { tokenValido: null, consultas: 0, solicitudes: [] }
  revisiones = {}
  const tokens = Object.fromEntries(Object.keys(USUARIOS).map((u) => [`token-${u}`, USUARIOS[u]]))

  const fetchFalso = vi.fn(async (url, opciones = {}) => {
    const { pathname, searchParams } = new URL(url)
    const metodo = opciones.method ?? 'GET'

    if (pathname === '/auth/login') {
      const f = new URLSearchParams(opciones.body)
      if (USUARIOS[f.get('username')] && f.get('password') === CONTRASENA)
        return respuesta(200, { access_token: `token-${f.get('username')}`, token_type: 'bearer', expira_en_minutos: 60 })
      return respuesta(401, { detail: 'Usuario o contraseña incorrectos' })
    }

    const usuario = tokens[(opciones.headers?.Authorization ?? '').replace('Bearer ', '')]
    if (!usuario || estado.tokenValido === false)
      return respuesta(401, { detail: 'Sesión no válida o vencida; vuelve a iniciar sesión' })
    const conDatos = usuario.rol !== 'admin_ti'
    const sinPermiso = () => respuesta(403, { detail: 'Tu rol no tiene acceso a datos de colaboradores' })

    if (pathname === '/auth/yo') return respuesta(200, usuario)
    if (pathname === '/areas') return respuesta(200, AREAS.filter((a) => usuario.areas_permitidas.includes(a.id)))
    if (pathname === '/periodos') return respuesta(200, PERIODOS)
    if (pathname === '/umbrales') return respuesta(200, UMBRALES)
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
