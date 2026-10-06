// Formato de cifras, fechas y estados para mostrar en pantalla.
// Los calculos los hace la API; aqui solo se presentan.

// Orden y agrupacion del tablero (seccion 10.2 del PRD). `base` describe que
// cuenta `n` en cada indicador, en singular y plural (ver backend/app/kpis.py).
const VACANTES = ['vacante cubierta', 'vacantes cubiertas']
const PROMEDIO = ['persona en promedio', 'personas en promedio']
export const INDICADORES = {
  tiempo_contratacion: { proceso: 'Reclutamiento', base: VACANTES },
  costo_por_contratacion: { proceso: 'Reclutamiento', base: VACANTES },
  cumplimiento_metas: { proceso: 'Desempeño', base: ['persona con metas', 'personas con metas'] },
  cobertura_capacitacion: { proceso: 'Capacitación', base: ['persona activa', 'personas activas'] },
  tasa_finalizacion: { proceso: 'Capacitación', base: ['inscripción', 'inscripciones'] },
  rotacion_total: { proceso: 'Rotación', base: PROMEDIO },
  rotacion_voluntaria: { proceso: 'Rotación', base: PROMEDIO },
  rotacion_involuntaria: { proceso: 'Rotación', base: PROMEDIO },
  enps: { proceso: 'Clima laboral', base: ['respuesta', 'respuestas'] },
  indice_productividad: { proceso: 'Productividad', base: ['persona equivalente', 'personas equivalentes'] },
}

export function ordenIndicador(indicador) {
  const i = Object.keys(INDICADORES).indexOf(indicador)
  return i === -1 ? 99 : i
}

// Semaforo (seccion 10.3.3). El color nunca va solo: siempre lleva icono y texto.
export const ESTADOS = {
  rojo: { etiqueta: 'Crítico', icono: '▲', clase: 'rojo' },
  amarillo: { etiqueta: 'Atención', icono: '●', clase: 'amarillo' },
  verde: { etiqueta: 'En rango', icono: '✓', clase: 'verde' },
  muestra_insuficiente: { etiqueta: 'Muestra insuficiente', icono: '○', clase: 'neutro' },
  suprimido: { etiqueta: 'Oculto por privacidad', icono: '—', clase: 'neutro' },
  sin_dato: { etiqueta: 'Sin dato', icono: '—', clase: 'neutro' },
}

export function infoEstado(estado) {
  return ESTADOS[estado] ?? { etiqueta: estado, icono: '•', clase: 'neutro' }
}

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
  'septiembre', 'octubre', 'noviembre', 'diciembre']
const MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

// "2026-04" o "2026-04-01" -> "abril 2026"
export function nombreMes(periodo) {
  const [anio, mes] = String(periodo).split('-').map(Number)
  return `${MESES[mes - 1]} ${anio}`
}

// "2026-04-01" -> "abr 26" (eje de las graficas)
export function mesCorto(periodo) {
  const [anio, mes] = String(periodo).split('-').map(Number)
  return `${MESES_CORTOS[mes - 1]} ${String(anio).slice(2)}`
}

// Quien pidio un reporte: una persona o la programacion mensual (RF-07)
export function solicitante(trabajo) {
  if (trabajo.solicitada_por) return trabajo.solicitada_por
  return trabajo.programada ? 'la programación mensual' : '—'
}

export function fechaHora(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' })
}

const numero = (valor, decimales) =>
  valor.toLocaleString('es-MX', { minimumFractionDigits: decimales, maximumFractionDigits: decimales })

// Valor de un indicador con su unidad: "12.3 %", "$21,500", "41 días", "+12 pts"
export function formatoValor(valor, unidad) {
  if (valor === null || valor === undefined) return '—'
  switch (unidad) {
    case '%':
      return `${numero(valor, 1)} %`
    case 'MXN':
      return `$${numero(valor, 0)}`
    case 'días':
      return `${numero(valor, 1)} días`
    case 'puntos':
      return `${valor > 0 ? '+' : ''}${numero(valor, 0)}`
    default:
      return numero(valor, 1)
  }
}

// Marca del eje de una grafica: sin decimales cuando el numero es redondo
export function formatoEje(valor, unidad) {
  if (!Number.isInteger(valor)) return formatoValor(valor, unidad)
  const v = valor.toLocaleString('es-MX')
  if (unidad === '%') return `${v} %`
  if (unidad === 'días') return `${v} días`
  return formatoValor(valor, unidad)
}

// Decimales con que se muestra la variacion de cada unidad
const DECIMALES_VARIACION = { '%': 1, MXN: 0, días: 1, puntos: 0 }

// Variacion redondeada como se muestra: un -0.04 pts se ve y se trata como 0
function redondear(variacion, unidad) {
  const d = DECIMALES_VARIACION[unidad] ?? 1
  return Math.round(variacion * 10 ** d) / 10 ** d
}

// Diferencia contra otro mes, en las unidades del indicador. En los
// porcentajes la diferencia son puntos ("pts"), igual que en la narrativa.
export function formatoVariacion(variacion, unidad) {
  if (variacion === null || variacion === undefined) return null
  const r = redondear(variacion, unidad)
  const signo = r > 0 ? '+' : r < 0 ? '−' : '±'
  const v = numero(Math.abs(r), DECIMALES_VARIACION[unidad] ?? 1)
  switch (unidad) {
    case '%':
    case 'puntos':
      return `${signo}${v} pts`
    case 'MXN':
      return `${signo}$${v}`
    case 'días':
      return `${signo}${v} días`
    default:
      return `${signo}${v}`
  }
}

// Si un cambio es bueno o malo depende del sentido del indicador:
// en rotacion subir es peor; en eNPS subir es mejor.
export function evolucion(variacion, sentido, unidad) {
  if (variacion === null || variacion === undefined || !sentido) return 'neutra'
  const r = redondear(variacion, unidad)
  if (r === 0) return 'neutra'
  const subirEsPeor = sentido === 'mayor_es_peor'
  return r > 0 === subirEsPeor ? 'empeora' : 'mejora'
}

export function formatoN(n, indicador) {
  const [singular, plural] = INDICADORES[indicador]?.base ?? ['registro', 'registros']
  return `${n.toLocaleString('es-MX')} ${n === 1 ? singular : plural}`
}
