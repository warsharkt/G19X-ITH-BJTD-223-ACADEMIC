import { evolucion, formatoN, formatoValor, formatoVariacion, INDICADORES } from '../formato'
import Semaforo from './Semaforo'

const TEXTO_EVOLUCION = { mejora: 'mejora', empeora: 'empeora', neutra: 'sin cambio' }
const FLECHA = { mejora: '↗', empeora: '↘', neutra: '→' }

function Variacion({ valor, unidad, sentido, contra }) {
  const texto = formatoVariacion(valor, unidad)
  if (texto === null) return <li className="variacion variacion-neutra">Sin dato {contra}</li>
  const ev = evolucion(valor, sentido, unidad)
  return (
    <li className={`variacion variacion-${ev}`}>
      <span aria-hidden="true">{FLECHA[ev]}</span> {texto} {contra}{' '}
      <span className="variacion-texto">({TEXTO_EVOLUCION[ev]})</span>
    </li>
  )
}

// Un indicador del mes: valor, semaforo, variaciones y base.
// Al pulsarla se elige el indicador de la grafica de tendencia.
export default function TarjetaKpi({ kpi, seleccionada, alElegir }) {
  const oculto = kpi.suprimido || kpi.valor === null
  return (
    <button
      type="button"
      className={`tarjeta-kpi${seleccionada ? ' tarjeta-seleccionada' : ''}`}
      aria-pressed={seleccionada}
      onClick={() => alElegir(kpi.indicador)}
    >
      <span className="tarjeta-encabezado">
        <span className="tarjeta-nombre">
          <span className="tarjeta-proceso">{INDICADORES[kpi.indicador]?.proceso}</span>
          {kpi.nombre}
        </span>
        <Semaforo estado={kpi.estado} pequeno />
      </span>
      <span className="tarjeta-valor">{oculto ? '—' : formatoValor(kpi.valor, kpi.unidad)}</span>
      {kpi.suprimido ? (
        <span className="tarjeta-nota">Se oculta porque el grupo tiene menos de 5 personas.</span>
      ) : (
        <>
          <ul className="variaciones">
            <Variacion valor={kpi.var_mes_ant} unidad={kpi.unidad} sentido={kpi.sentido} contra="vs mes anterior" />
            <Variacion valor={kpi.var_anio_ant} unidad={kpi.unidad} sentido={kpi.sentido} contra="vs año anterior" />
          </ul>
          <span className="tarjeta-nota">
            {formatoN(kpi.n, kpi.indicador)}
            {kpi.estado === 'muestra_insuficiente' && ' · muy pocas para el semáforo'}
          </span>
        </>
      )}
    </button>
  )
}
