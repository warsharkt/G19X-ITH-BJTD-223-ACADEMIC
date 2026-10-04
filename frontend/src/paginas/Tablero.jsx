import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import GraficaSerie from '../componentes/GraficaSerie'
import Mensaje from '../componentes/Mensaje'
import TarjetaKpi from '../componentes/TarjetaKpi'
import { nombreMes, ordenIndicador } from '../formato'
import { useConsulta } from '../useConsulta'

const PRIORIDAD = { rojo: 0, amarillo: 1 }

// Indicador que se grafica si no se eligio uno: el mas grave del mes
function indicadorInicial(kpis) {
  const ordenados = [...kpis].sort(
    (a, b) => (PRIORIDAD[a.estado] ?? 9) - (PRIORIDAD[b.estado] ?? 9) || ordenIndicador(a.indicador) - ordenIndicador(b.indicador),
  )
  return ordenados[0]?.indicador
}

function Resumen({ kpis }) {
  const cuenta = (estado) => kpis.filter((k) => k.estado === estado).length
  const otros = kpis.length - cuenta('rojo') - cuenta('amarillo') - cuenta('verde')
  return (
    <ul className="resumen-estados" aria-label="Resumen del semáforo">
      <li className="resumen-rojo">
        <strong>{cuenta('rojo')}</strong> en crítico
      </li>
      <li className="resumen-amarillo">
        <strong>{cuenta('amarillo')}</strong> en atención
      </li>
      <li className="resumen-verde">
        <strong>{cuenta('verde')}</strong> en rango
      </li>
      {otros > 0 && (
        <li className="resumen-neutro">
          <strong>{otros}</strong> sin semáforo
        </li>
      )}
    </ul>
  )
}

export default function Tablero() {
  const navegar = useNavigate()
  const [parametros, setParametros] = useSearchParams()
  const [solicitando, setSolicitando] = useState(false)
  const [errorSolicitud, setErrorSolicitud] = useState(null)

  const areas = useConsulta(() => api.areas(), [])
  const periodos = useConsulta(() => api.periodos(), [])
  const umbrales = useConsulta(() => api.umbrales(), [])

  // Filtros en la URL: se pueden compartir y sobreviven al recargar
  const areaId = parametros.has('area') ? Number(parametros.get('area')) : areas.datos?.[0]?.id
  const periodo = parametros.get('periodo') ?? periodos.datos?.at(-1)
  const listo = Boolean(areas.datos && periodos.datos) && areaId !== undefined && periodo !== undefined

  const kpis = useConsulta(listo ? () => api.kpis(periodo, areaId) : null, [periodo, areaId])
  const filas = kpis.datos ?? []
  const indicador = parametros.get('indicador') ?? indicadorInicial(filas)
  const kpiElegido = filas.find((k) => k.indicador === indicador)
  const serie = useConsulta(indicador && listo ? () => api.serie(indicador, areaId) : null, [indicador, areaId])

  function cambiar(campo, valor) {
    const nuevos = new URLSearchParams(parametros)
    nuevos.set(campo, valor)
    setParametros(nuevos, { replace: true })
  }

  async function generarNarrativa() {
    setErrorSolicitud(null)
    setSolicitando(true)
    try {
      const trabajo = await api.solicitarNarrativa(periodo, areaId)
      navegar(`/narrativas/${trabajo.id}`)
    } catch (err) {
      setErrorSolicitud(err.message)
      setSolicitando(false)
    }
  }

  const errorCatalogo = areas.error || periodos.error
  if (errorCatalogo) return <Mensaje titulo="No se pudo cargar el tablero">{errorCatalogo.message}</Mensaje>
  if (!listo) return <p className="cargando">Cargando…</p>

  const nombreArea = areas.datos.find((a) => a.id === areaId)?.nombre ?? `Área ${areaId}`
  const tarjetas = [...filas].sort((a, b) => ordenIndicador(a.indicador) - ordenIndicador(b.indicador))
  const umbral = umbrales.datos?.find((u) => u.indicador === indicador)

  return (
    <div className="tablero">
      <div className="titulo-pagina">
        <div>
          <h1>Indicadores de {nombreArea}</h1>
          <p className="texto-secundario">{nombreMes(periodo)}</p>
        </div>
        <button type="button" className="boton-primario" onClick={generarNarrativa} disabled={solicitando}>
          {solicitando ? 'Solicitando…' : 'Generar reporte con IA'}
        </button>
      </div>
      {errorSolicitud && <Mensaje titulo="No se pudo solicitar el reporte">{errorSolicitud}</Mensaje>}

      <div className="filtros" role="group" aria-label="Filtros">
        <label>
          Área
          <select value={areaId} onChange={(e) => cambiar('area', e.target.value)} disabled={areas.datos.length < 2}>
            {areas.datos.map((a) => (
              <option key={a.id} value={a.id}>
                {a.nombre}
              </option>
            ))}
          </select>
        </label>
        <label>
          Mes
          <select value={periodo} onChange={(e) => cambiar('periodo', e.target.value)}>
            {[...periodos.datos].reverse().map((p) => (
              <option key={p} value={p}>
                {nombreMes(p)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Indicador
          <select value={indicador ?? ''} onChange={(e) => cambiar('indicador', e.target.value)}>
            {tarjetas.map((k) => (
              <option key={k.indicador} value={k.indicador}>
                {k.nombre}
              </option>
            ))}
          </select>
        </label>
      </div>

      {kpis.error && <Mensaje titulo="No se pudieron cargar los indicadores">{kpis.error.message}</Mensaje>}

      <div className={kpis.cargando ? 'recargando' : undefined}>
        {filas.length > 0 && <Resumen kpis={filas} />}

        {kpiElegido && serie.datos && (
          <GraficaSerie serie={serie.datos} kpi={kpiElegido} umbral={umbral} periodoSeleccionado={periodo} />
        )}
        {serie.error && <Mensaje titulo="No se pudo cargar la tendencia">{serie.error.message}</Mensaje>}

        <h2 className="oculto-visual">Indicadores del mes</h2>
        <div className="rejilla-kpi">
          {tarjetas.map((k) => (
            <TarjetaKpi
              key={k.indicador}
              kpi={k}
              seleccionada={k.indicador === indicador}
              alElegir={(i) => cambiar('indicador', i)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
