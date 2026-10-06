import { useState } from 'react'
import { api } from '../api'
import Mensaje from '../componentes/Mensaje'
import { fechaHora, formatoValor, INDICADORES, nombreMes, ordenIndicador } from '../formato'
import { puedeVerDatos, useSesion } from '../sesion'
import { useConsulta } from '../useConsulta'

const SENTIDO = { mayor_es_peor: 'Peor si sube', menor_es_peor: 'Peor si baja' }
const ORIGEN = { api: 'Servidor', script: 'Programador de tareas' }
const DIAS = Array.from({ length: 28 }, (_, i) => i + 1)

// Umbrales del semaforo (seccion 10.2 del PRD). RRHH los edita fila por
// fila; la API valida que tengan sentido y registra cada cambio.
function Umbrales({ editable, alGuardar }) {
  const [version, setVersion] = useState(0)
  const umbrales = useConsulta(() => api.umbrales(), [version])
  const [edicion, setEdicion] = useState(null) // { indicador, atencion, critico }
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState(null)

  function editar(u) {
    setError(null)
    setEdicion({ indicador: u.indicador, atencion: String(u.umbral_atencion), critico: String(u.umbral_critico) })
  }

  async function guardar() {
    const atencion = Number(edicion.atencion)
    const critico = Number(edicion.critico)
    if (edicion.atencion.trim() === '' || edicion.critico.trim() === '' || !isFinite(atencion) || !isFinite(critico)) {
      setError('Escribe los dos umbrales como números')
      return
    }
    setError(null)
    setGuardando(true)
    try {
      await api.actualizarUmbral(edicion.indicador, atencion, critico)
      setEdicion(null)
      setVersion((v) => v + 1)
      alGuardar()
    } catch (err) {
      setError(err.message)
    } finally {
      setGuardando(false)
    }
  }

  const campo = (u, llave, etiqueta) => (
    <input
      type="number"
      step="any"
      inputMode="decimal"
      className="entrada-umbral"
      aria-label={`${etiqueta} de ${u.nombre}`}
      value={edicion[llave]}
      onChange={(e) => setEdicion({ ...edicion, [llave]: e.target.value })}
      onKeyDown={(e) => e.key === 'Enter' && guardar()}
    />
  )

  return (
    <section className="seccion">
      <h2>Umbrales del semáforo</h2>
      <p className="texto-secundario">
        Valores que definen cuándo un indicador pasa a atención o a crítico. Un indicador en rojo genera un aviso para
        quien le corresponde.
      </p>
      {umbrales.error && <Mensaje>{umbrales.error.message}</Mensaje>}
      {error && <Mensaje>{error}</Mensaje>}
      {umbrales.datos && (
        <div className="panel tabla-desplazable">
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">Proceso</th>
                <th scope="col">Indicador</th>
                <th scope="col">Sentido</th>
                <th scope="col" className="num">Atención</th>
                <th scope="col" className="num">Crítico</th>
                {editable && <th scope="col"><span className="oculto-visual">Acciones</span></th>}
              </tr>
            </thead>
            <tbody>
              {[...umbrales.datos]
                .sort((a, b) => ordenIndicador(a.indicador) - ordenIndicador(b.indicador))
                .map((u) => {
                  const enEdicion = edicion?.indicador === u.indicador
                  return (
                    <tr key={u.indicador}>
                      <td>{INDICADORES[u.indicador]?.proceso ?? '—'}</td>
                      <td>{u.nombre}</td>
                      <td>{SENTIDO[u.sentido] ?? u.sentido}</td>
                      <td className="num">
                        {enEdicion ? campo(u, 'atencion', 'Atención') : formatoValor(u.umbral_atencion, u.unidad)}
                      </td>
                      <td className="num">
                        {enEdicion ? campo(u, 'critico', 'Crítico') : formatoValor(u.umbral_critico, u.unidad)}
                      </td>
                      {editable && (
                        <td className="acciones">
                          {enEdicion ? (
                            <>
                              <button type="button" className="boton-primario" disabled={guardando} onClick={guardar}>
                                {guardando ? 'Guardando…' : 'Guardar'}
                              </button>
                              <button type="button" className="boton-texto" onClick={() => setEdicion(null)}>
                                Cancelar
                              </button>
                            </>
                          ) : (
                            <button
                              type="button"
                              className="boton-texto"
                              aria-label={`Editar ${u.nombre}`}
                              disabled={guardando}
                              onClick={() => editar(u)}
                            >
                              Editar
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  )
                })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// Bitacora: quien cambio cada umbral, cuando y de que valores a cuales
function CambiosUmbrales({ version }) {
  const cambios = useConsulta(() => api.cambiosUmbrales(), [version])
  return (
    <section className="seccion">
      <h2>Cambios de umbrales</h2>
      {cambios.error && <Mensaje>{cambios.error.message}</Mensaje>}
      {cambios.datos?.length === 0 && <p className="nota">Todavía no se ha cambiado ningún umbral.</p>}
      {cambios.datos?.length > 0 && (
        <div className="panel tabla-desplazable">
          <table className="tabla" aria-label="Cambios de umbrales">
            <thead>
              <tr>
                <th scope="col">Fecha</th>
                <th scope="col">Indicador</th>
                <th scope="col">Antes (atención / crítico)</th>
                <th scope="col">Después (atención / crítico)</th>
                <th scope="col">Quién</th>
              </tr>
            </thead>
            <tbody>
              {cambios.datos.map((c) => (
                <tr key={c.id}>
                  <td>{fechaHora(c.cambiado_en)}</td>
                  <td>{c.nombre}</td>
                  <td>
                    {formatoValor(c.atencion_antes, c.unidad)} / {formatoValor(c.critico_antes, c.unidad)}
                  </td>
                  <td>
                    {formatoValor(c.atencion_nuevo, c.unidad)} / {formatoValor(c.critico_nuevo, c.unidad)}
                  </td>
                  <td>{c.usuario}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// Programacion mensual de reportes (RF-07)
function Programacion({ editable }) {
  const [version, setVersion] = useState(0)
  const programacion = useConsulta(() => api.programacion(), [version])
  const [borrador, setBorrador] = useState(null) // { activa, dia } mientras se edita
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState(null)
  const [guardado, setGuardado] = useState(false)

  const datos = programacion.datos
  const valores = borrador ?? (datos && { activa: datos.activa, dia: datos.dia_del_mes })
  const cambio = (campos) => {
    setGuardado(false)
    setBorrador({ ...valores, ...campos })
  }

  async function guardar(e) {
    e.preventDefault()
    setError(null)
    setGuardando(true)
    try {
      await api.guardarProgramacion(valores.activa, valores.dia)
      setBorrador(null)
      setGuardado(true)
      setVersion((v) => v + 1)
    } catch (err) {
      setError(err.message)
    } finally {
      setGuardando(false)
    }
  }

  return (
    <section className="seccion">
      <h2>Programación mensual</h2>
      <p className="texto-secundario">
        Cada mes, a partir del día elegido, se generan solos los reportes del último mes cerrado con datos: el
        consolidado y cada área. Nacen pendientes de revisión y Recursos Humanos recibe un aviso cuando cada uno está
        listo.
      </p>
      {programacion.error && <Mensaje>{programacion.error.message}</Mensaje>}
      {datos && (
        <div className="panel">
          {editable ? (
            <form className="formulario-programacion" onSubmit={guardar}>
              <label className="campo-casilla">
                <input type="checkbox" checked={valores.activa} onChange={(e) => cambio({ activa: e.target.checked })} />
                Generar los reportes cada mes
              </label>
              <label>
                A partir del día
                <select value={valores.dia} onChange={(e) => cambio({ dia: Number(e.target.value) })}>
                  {DIAS.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </label>
              <button type="submit" className="boton-primario" disabled={guardando || !borrador}>
                {guardando ? 'Guardando…' : 'Guardar'}
              </button>
            </form>
          ) : (
            <p>
              <strong>{datos.activa ? 'Activa' : 'Desactivada'}</strong>
              {datos.activa && `: a partir del día ${datos.dia_del_mes} de cada mes`}
            </p>
          )}
          {error && <Mensaje>{error}</Mensaje>}
          {guardado && <Mensaje tipo="exito">Programación guardada.</Mensaje>}
          <p className="nota">
            {datos.modificada_por
              ? `Último cambio: ${datos.modificada_por}, ${fechaHora(datos.modificada_en)}. `
              : 'Nunca se ha cambiado. '}
            {datos.correo_activo
              ? 'Además de los avisos en el sistema, se envía un correo sin datos a quien tenga correo registrado.'
              : 'Los avisos solo se ven en el sistema: el servidor no tiene correo configurado.'}
          </p>
          {datos.corridas.length > 0 && (
            <div className="tabla-desplazable">
              <table className="tabla" aria-label="Meses generados">
                <thead>
                  <tr>
                    <th scope="col">Mes</th>
                    <th scope="col" className="num">Reportes</th>
                    <th scope="col">Generados el</th>
                    <th scope="col">Desde</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.corridas.map((c) => (
                    <tr key={c.periodo}>
                      <td>{nombreMes(c.periodo)}</td>
                      <td className="num">{c.narrativas}</td>
                      <td>{fechaHora(c.iniciada_en)}</td>
                      <td>{ORIGEN[c.origen] ?? c.origen}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

// Panel de configuracion (RF-12). Todos la ven; solo RRHH la cambia: un umbral
// decide que se pinta de rojo y a quien le llega una alerta (regla 10.3.3).
export default function Configuracion() {
  const { usuario } = useSesion()
  const editable = usuario.rol === 'rrhh'
  const [cambios, setCambios] = useState(0)

  return (
    <div>
      <div className="titulo-pagina">
        <div>
          <h1>Configuración</h1>
          <p className="texto-secundario">
            {editable
              ? 'Los cambios quedan registrados con tu usuario.'
              : 'Solo Recursos Humanos puede cambiar esta configuración.'}
          </p>
        </div>
      </div>
      {!puedeVerDatos(usuario) && (
        <Mensaje tipo="info">
          Tu rol administra catálogos y configuración; no tiene acceso a datos de colaboradores.
        </Mensaje>
      )}
      <Umbrales editable={editable} alGuardar={() => setCambios((v) => v + 1)} />
      <CambiosUmbrales version={cambios} />
      <Programacion editable={editable} />
    </div>
  )
}
