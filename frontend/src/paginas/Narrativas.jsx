import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import Mensaje from '../componentes/Mensaje'
import { fechaHora, nombreMes } from '../formato'
import { useConsulta } from '../useConsulta'

// Estado de cada reporte: primero la generacion y, si termino, la revision
const ESTADOS = {
  en_proceso: { texto: 'En proceso', clase: 'neutro', icono: '◌' },
  error: { texto: 'Error al generar', clase: 'rojo', icono: '✕' },
  pendiente: { texto: 'Pendiente de revisión', clase: 'amarillo', icono: '●' },
  aprobada: { texto: 'Aprobado', clase: 'verde', icono: '✓' },
  rechazada: { texto: 'Rechazado', clase: 'rojo', icono: '✕' },
}

function estadoDe(t) {
  return ESTADOS[t.estado === 'lista' ? t.revision : t.estado] ?? { texto: t.estado, clase: 'neutro', icono: '•' }
}

function duracion(t) {
  if (!t.terminada_en) return '—'
  const s = Math.round((new Date(t.terminada_en) - new Date(t.solicitada_en)) / 1000)
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`
}

function NuevoReporte({ areas, periodos }) {
  const navegar = useNavigate()
  const [areaId, setAreaId] = useState(areas[0].id)
  const [periodo, setPeriodo] = useState(periodos.at(-1))
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState(null)

  async function enviar(e) {
    e.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      const t = await api.solicitarNarrativa(periodo, Number(areaId))
      navegar(`/narrativas/${t.id}`)
    } catch (err) {
      setError(err.message)
      setEnviando(false)
    }
  }

  return (
    <form className="panel nuevo-reporte" onSubmit={enviar}>
      <h2>Nuevo reporte</h2>
      <div className="filtros">
        <label>
          Área
          <select value={areaId} onChange={(e) => setAreaId(e.target.value)} disabled={areas.length < 2}>
            {areas.map((a) => (
              <option key={a.id} value={a.id}>
                {a.nombre}
              </option>
            ))}
          </select>
        </label>
        <label>
          Mes
          <select value={periodo} onChange={(e) => setPeriodo(e.target.value)}>
            {[...periodos].reverse().map((p) => (
              <option key={p} value={p}>
                {nombreMes(p)}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="boton-primario" disabled={enviando}>
          {enviando ? 'Solicitando…' : 'Generar con IA'}
        </button>
      </div>
      {error && <Mensaje>{error}</Mensaje>}
    </form>
  )
}

// Historial de reportes (RF-10): consultable por area y mes.
export default function Narrativas() {
  const [parametros, setParametros] = useSearchParams()
  const areaFiltro = parametros.get('area') ?? ''
  const periodoFiltro = parametros.get('periodo') ?? ''
  const revisionFiltro = parametros.get('revision') ?? ''
  const [vuelta, setVuelta] = useState(0) // fuerza una nueva consulta

  const areas = useConsulta(() => api.areas(), [])
  const periodos = useConsulta(() => api.periodos(), [])
  const historial = useConsulta(
    () => api.historial({ areaId: areaFiltro, periodo: periodoFiltro, revision: revisionFiltro }),
    [areaFiltro, periodoFiltro, revisionFiltro, vuelta],
  )

  // Mientras haya reportes en proceso, el historial se actualiza solo
  const hayEnProceso = historial.datos?.some((t) => t.estado === 'en_proceso')
  useEffect(() => {
    if (!hayEnProceso) return
    const t = setTimeout(() => setVuelta((v) => v + 1), 10000)
    return () => clearTimeout(t)
  }, [hayEnProceso, historial.datos])

  function filtrar(campo, valor) {
    const nuevos = new URLSearchParams(parametros)
    if (valor === '') nuevos.delete(campo)
    else nuevos.set(campo, valor)
    setParametros(nuevos, { replace: true })
  }

  const nombreArea = (id) => areas.datos?.find((a) => a.id === id)?.nombre ?? `Área ${id}`
  const error = areas.error || periodos.error || historial.error

  return (
    <div className="narrativas">
      <div className="titulo-pagina">
        <div>
          <h1>Reportes con IA</h1>
          <p className="texto-secundario">
            Narrativas ejecutivas redactadas por IA a partir de los indicadores. Solo se distribuyen las que aprueba
            una persona de RRHH distinta de quien las solicitó.
          </p>
        </div>
      </div>

      {areas.datos && periodos.datos && <NuevoReporte areas={areas.datos} periodos={periodos.datos} />}
      {error && <Mensaje>{error.message}</Mensaje>}

      <section className="panel">
        <h2>Historial</h2>
        <div className="filtros" role="group" aria-label="Filtros del historial">
          <label>
            Área
            <select value={areaFiltro} onChange={(e) => filtrar('area', e.target.value)}>
              <option value="">Todas</option>
              {areas.datos?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.nombre}
                </option>
              ))}
            </select>
          </label>
          <label>
            Mes
            <select value={periodoFiltro} onChange={(e) => filtrar('periodo', e.target.value)}>
              <option value="">Todos</option>
              {periodos.datos &&
                [...periodos.datos].reverse().map((p) => (
                  <option key={p} value={p}>
                    {nombreMes(p)}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Revisión
            <select value={revisionFiltro} onChange={(e) => filtrar('revision', e.target.value)}>
              <option value="">Todas</option>
              <option value="pendiente">Pendientes de revisión</option>
              <option value="aprobada">Aprobados</option>
              <option value="rechazada">Rechazados</option>
            </select>
          </label>
        </div>

        {historial.datos?.length === 0 && <p className="texto-secundario">Todavía no hay reportes con estos filtros.</p>}
        {historial.datos?.length > 0 && (
          <div className={`tabla-desplazable${historial.cargando ? ' recargando' : ''}`}>
            <table className="tabla">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">Área</th>
                  <th scope="col">Mes</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Solicitado por</th>
                  <th scope="col">Revisado por</th>
                  <th scope="col">Solicitado</th>
                  <th scope="col" className="num">Duración</th>
                </tr>
              </thead>
              <tbody>
                {historial.datos.map((t) => {
                  const e = estadoDe(t)
                  return (
                    <tr key={t.id}>
                      <td>
                        <Link to={`/narrativas/${t.id}`}>#{t.id}</Link>
                      </td>
                      <td>{nombreArea(t.area_id)}</td>
                      <td>{nombreMes(t.periodo)}</td>
                      <td>
                        <span className={`semaforo semaforo-${e.clase} semaforo-pequeno`}>
                          <span className="semaforo-icono" aria-hidden="true">
                            {e.icono}
                          </span>
                          {e.texto}
                        </span>
                      </td>
                      <td>{t.solicitada_por ?? '—'}</td>
                      <td>{t.revisada_por ?? '—'}</td>
                      <td>{fechaHora(t.solicitada_en)}</td>
                      <td className="num">{duracion(t)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
