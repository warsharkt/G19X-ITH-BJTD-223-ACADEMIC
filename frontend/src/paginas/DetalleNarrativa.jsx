import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import Mensaje from '../componentes/Mensaje'
import PanelRevision from '../componentes/PanelRevision'
import VistaNarrativa from '../componentes/VistaNarrativa'
import { fechaHora, nombreMes, solicitante } from '../formato'
import { useConsulta } from '../useConsulta'

export const SEGUNDOS_ENTRE_CONSULTAS = 5

// Etapas que ve quien espera: avanzar por pasos con nombre se siente mas
// corto que un cronometro. La barra avanza rapido al principio y se frena
// cerca del final (nunca llega al 100 % hasta que el reporte esta listo).
export const ETAPAS = [
  [0, 'Reuniendo los indicadores del mes'],
  [0.12, 'Analizando tendencias y alertas'],
  [0.35, 'Redactando el resumen ejecutivo'],
  [0.75, 'Verificando cada cifra contra los datos'],
]
const SEGUNDOS_CARACTERISTICOS = 240

export function avance(segundos) {
  return Math.min(0.95, 1 - Math.exp(-Math.max(0, segundos) / SEGUNDOS_CARACTERISTICOS))
}

function EsperaReporte({ trabajo, alcance }) {
  const [ahora, setAhora] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setAhora(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const p = avance((ahora - new Date(trabajo.solicitada_en).getTime()) / 1000)
  const actual = ETAPAS.findLastIndex(([desde]) => p >= desde)
  const firma = trabajo.firma

  return (
    <div className="en-proceso" role="status">
      <h1>Preparando el reporte de {alcance}</h1>
      <div
        className="barra-avance"
        role="progressbar"
        aria-label="Avance del reporte"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(p * 100)}
      >
        <span style={{ width: `${Math.round(p * 100)}%` }} />
      </div>
      <ol className="etapas">
        {ETAPAS.map(([, texto], i) => (
          <li key={texto} className={i < actual ? 'hecha' : i === actual ? 'actual' : 'pendiente'}>
            <span className="etapa-icono" aria-hidden="true">
              {i < actual ? '✓' : i === actual ? <span className="girando" /> : ''}
            </span>
            {texto}
            {i < actual && <span className="oculto-visual"> (terminado)</span>}
          </li>
        ))}
      </ol>
      <p>
        {firma ? (
          <>
            Al terminar se enviará a <strong>{firma.nombre}</strong> ({firma.cargo}) para su firma.
          </>
        ) : (
          'Al terminar quedará pendiente de la firma de la Responsable de RRHH.'
        )}{' '}
        Puedes seguir trabajando: te avisaremos cuando esté firmado.
      </p>
    </div>
  )
}

// Una solicitud de narrativa: mientras esta en proceso se consulta cada pocos
// segundos; cuando termina muestra el reporte o el motivo del error.
export default function DetalleNarrativa() {
  const { id } = useParams()
  const [trabajo, setTrabajo] = useState(null)
  const [error, setError] = useState(null)
  const areas = useConsulta(() => api.areas(), [])

  useEffect(() => {
    let vigente = true
    let temporizador
    async function consultar() {
      try {
        const t = await api.narrativa(id)
        if (!vigente) return
        setTrabajo(t)
        setError(null)
        if (t.estado === 'en_proceso') temporizador = setTimeout(consultar, SEGUNDOS_ENTRE_CONSULTAS * 1000)
      } catch (err) {
        if (vigente) setError(err)
      }
    }
    setTrabajo(null)
    consultar()
    return () => {
      vigente = false
      clearTimeout(temporizador)
    }
  }, [id])

  const volver = (
    <p>
      <Link to="/narrativas">← Volver al historial</Link>
    </p>
  )

  if (error)
    return (
      <>
        {volver}
        <Mensaje titulo="No se pudo abrir el reporte">{error.message}</Mensaje>
      </>
    )
  if (!trabajo) return <p className="cargando">Cargando…</p>
  const alcance = `${areas.datos?.find((a) => a.id === trabajo.area_id)?.nombre ?? `área ${trabajo.area_id}`}, ${nombreMes(trabajo.periodo)}`

  if (trabajo.estado === 'en_proceso')
    return (
      <>
        {volver}
        <EsperaReporte trabajo={trabajo} alcance={alcance} />
      </>
    )

  if (trabajo.estado === 'error')
    return (
      <>
        {volver}
        <Mensaje titulo={`El reporte #${trabajo.id} (${alcance}) no se pudo generar`}>
          <p>{trabajo.error}</p>
          {trabajo.detalle_error?.length > 0 && (
            <ul>
              {trabajo.detalle_error.map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
          )}
          <p className="nota">
            Solicitado por {solicitante(trabajo)} el {fechaHora(trabajo.solicitada_en)}. El sistema nunca
            rellena el reporte con texto que no haya redactado la IA; puedes volver a solicitarlo.
          </p>
        </Mensaje>
      </>
    )

  return (
    <>
      {volver}
      <VistaNarrativa narrativa={trabajo.narrativa} aviso={<PanelRevision trabajo={trabajo} alRevisar={setTrabajo} />} />
      <p className="nota bitacora">
        Reporte #{trabajo.id} · solicitado por {solicitante(trabajo)} el {fechaHora(trabajo.solicitada_en)} ·
        terminado el {fechaHora(trabajo.terminada_en)}
        {trabajo.revisada_por &&
          ` · ${trabajo.revision} por ${trabajo.firma?.nombre ?? trabajo.revisada_por} el ${fechaHora(trabajo.revisada_en)}`}
      </p>
    </>
  )
}
