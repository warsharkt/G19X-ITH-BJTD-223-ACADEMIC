import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import Mensaje from '../componentes/Mensaje'
import PanelRevision from '../componentes/PanelRevision'
import VistaNarrativa from '../componentes/VistaNarrativa'
import { fechaHora, nombreMes, solicitante } from '../formato'
import { useConsulta } from '../useConsulta'

export const SEGUNDOS_ENTRE_CONSULTAS = 5

function Transcurrido({ desde }) {
  const [ahora, setAhora] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setAhora(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  const s = Math.max(0, Math.round((ahora - new Date(desde).getTime()) / 1000))
  return (
    <>
      {Math.floor(s / 60)} min {String(s % 60).padStart(2, '0')} s
    </>
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
        <div className="en-proceso" role="status">
          <span className="girando" aria-hidden="true" />
          <div>
            <h1>Redactando el reporte de {alcance}…</h1>
            <p>
              Tiempo transcurrido: <Transcurrido desde={trabajo.solicitada_en} />. Con el modelo local en CPU suele
              tardar varios minutos.
            </p>
            <p className="texto-secundario">
              Puedes salir de esta página: la generación sigue en segundo plano y el reporte quedará en el historial.
            </p>
          </div>
        </div>
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
          ` · ${trabajo.revision} por ${trabajo.revisada_por} el ${fechaHora(trabajo.revisada_en)}`}
      </p>
    </>
  )
}
