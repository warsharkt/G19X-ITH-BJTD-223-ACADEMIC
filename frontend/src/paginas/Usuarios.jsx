import { useState } from 'react'
import { api } from '../api'
import Mensaje from '../componentes/Mensaje'
import { fechaHora } from '../formato'
import { cargoDe, NOMBRES_ROL, useSesion } from '../sesion'
import { useConsulta } from '../useConsulta'

// Lo que le paso a la cuenta; quien lo hizo va en su propia columna
const ACCIONES = {
  crear: 'Cuenta creada',
  modificar: 'Cuenta modificada',
  desactivar: 'Cuenta desactivada',
  reactivar: 'Cuenta reactivada',
  restablecer_contrasena: 'Contraseña restablecida',
  cambiar_contrasena: 'Contraseña cambiada',
  activar_mfa: 'Verificación en dos pasos activada',
  reiniciar_mfa: 'Verificación en dos pasos reiniciada',
  usar_codigo_respaldo: 'Entrada con un código de respaldo',
  designar_suplente: 'Designada suplente para firmar reportes',
  terminar_suplencia: 'Suplencia terminada',
  dar_firma: 'Permiso de firma dado',
  quitar_firma: 'Permiso de firma quitado',
  suspender_firma: 'Permiso de firma suspendido',
  aprobar_acceso: 'Acceso aprobado',
  crear_area: 'Área agregada',
  renombrar_area: 'Área renombrada',
  rechazar_acceso: 'Acceso rechazado',
}

// Cambios que no hizo una persona desde el tablero
function quien(hechoPor) {
  if (hechoPor.startsWith('arranque:')) return 'El sistema, al arrancar'
  if (hechoPor.startsWith('consola:')) return `Consola del servidor (${hechoPor.slice('consola:'.length)})`
  return hechoPor
}
const CAMPOS = {
  nombre: 'nombre', rol: 'rol', area_id: 'área', correo: 'correo', activo: 'activa', firma_reportes: 'firma reportes',
  desde: 'desde', hasta: 'hasta', motivo: 'motivo', suplencias_canceladas: 'suplencias canceladas',
}
const VACIA = { usuario: '', nombre: '', rol: 'gerente', area_id: '', correo: '' }

// TI no elige quien firma: el permiso lo da una Responsable de RRHH desde
// esta misma pantalla (regla 10.3.9). Asi una sola persona de TI no puede
// crearse una cuenta que firme reportes.
const OPCIONES_ROL = [
  ['rrhh', NOMBRES_ROL.rrhh],
  ['direccion', NOMBRES_ROL.direccion],
  ['gerente', NOMBRES_ROL.gerente],
  ['admin_ti', NOMBRES_ROL.admin_ti],
]

// Detalle de la bitacora en palabras: "rol: Gerencia de área → Recursos Humanos"
function detalle(c, nombreArea) {
  const valor = (campo, v) => {
    if (v === null || v === undefined || v === '') return '—'
    if (campo === 'rol') return NOMBRES_ROL[v] ?? v
    if (campo === 'area_id') return nombreArea(v)
    if (campo === 'activo' || campo === 'firma_reportes') return v ? 'sí' : 'no'
    return String(v)
  }
  return Object.entries(c.detalle)
    .map(([campo, v]) =>
      Array.isArray(v)
        ? `${CAMPOS[campo] ?? campo}: ${valor(campo, v[0])} → ${valor(campo, v[1])}`
        : `${CAMPOS[campo] ?? campo}: ${valor(campo, v)}`,
    )
    .join(' · ')
}

// Alta o edicion de una cuenta. Al crearla, la API genera la contrasena temporal.
function FormularioCuenta({ inicial, areas, alGuardar, alCancelar, nueva }) {
  const [datos, setDatos] = useState(inicial)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState(null)
  const cambio = (campo) => (e) => setDatos({ ...datos, [campo]: e.target.value })

  async function enviar(e) {
    e.preventDefault()
    setError(null)
    setGuardando(true)
    try {
      await alGuardar({
        ...(nueva ? { usuario: datos.usuario.trim() } : {}),
        nombre: datos.nombre.trim(),
        rol: datos.rol,
        area_id: datos.rol === 'gerente' && datos.area_id !== '' ? Number(datos.area_id) : null,
        correo: datos.correo.trim() || null,
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setGuardando(false)
    }
  }

  return (
    <form className="formulario-cuenta" onSubmit={enviar}>
      {error && <Mensaje>{error}</Mensaje>}
      <div className="campos-cuenta">
        {nueva && (
          <label>
            Usuario
            <input value={datos.usuario} onChange={cambio('usuario')} required autoComplete="off" />
          </label>
        )}
        <label>
          Nombre
          <input value={datos.nombre} onChange={cambio('nombre')} required />
        </label>
        <label>
          Rol
          <select value={datos.rol} onChange={cambio('rol')}>
            {OPCIONES_ROL.map(([rol, nombre]) => (
              <option key={rol} value={rol}>
                {nombre}
              </option>
            ))}
          </select>
          {datos.rol === 'rrhh' && (
            <span className="nota">Entra como Analista. El permiso de firmar se lo da una Responsable de RRHH.</span>
          )}
        </label>
        {datos.rol === 'gerente' && (
          <label>
            Área
            <select value={datos.area_id ?? ''} onChange={cambio('area_id')} required>
              <option value="">Elige un área</option>
              {areas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.nombre}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Correo (opcional)
          <input type="email" value={datos.correo ?? ''} onChange={cambio('correo')} />
        </label>
      </div>
      <div className="botones">
        <button type="submit" className="boton-primario" disabled={guardando}>
          {guardando ? 'Guardando…' : nueva ? 'Crear cuenta' : 'Guardar cambios'}
        </button>
        <button type="button" className="boton-texto" onClick={alCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  )
}

// Cuentas del sistema (RF-12) y su bitacora (RF-11). Solo TI las administra:
// quien administra cuentas no aprueba reportes. RRHH las consulta para auditar.
export default function Usuarios() {
  const { usuario } = useSesion()
  const esTi = usuario.rol === 'admin_ti'
  const esResponsable = usuario.rol === 'rrhh' && usuario.firma_reportes
  const [version, setVersion] = useState(0)
  const cuentas = useConsulta(() => api.cuentas(), [version])
  const cambios = useConsulta(() => api.cambiosCuentas(), [version])
  const accesos = useConsulta(() => api.accesos(), [version])
  const catalogo = useConsulta(() => api.areas(), [])
  const [formulario, setFormulario] = useState(null) // 'nueva' o la cuenta en edicion
  const [temporal, setTemporal] = useState(null) // { nombre, contrasena } se muestra una vez
  const [error, setError] = useState(null)

  const areas = (catalogo.datos ?? []).filter((a) => a.id !== 0)
  const nombreArea = (id) => areas.find((a) => a.id === id)?.nombre ?? `Área ${id}`
  const recargar = () => setVersion((v) => v + 1)

  async function accion(fn, confirmacion) {
    if (confirmacion && !window.confirm(confirmacion)) return
    setError(null)
    try {
      await fn()
      recargar()
    } catch (err) {
      setError(err.message)
    }
  }

  async function crear(datos) {
    const r = await api.crearCuenta(datos)
    setTemporal({ nombre: r.cuenta.nombre, contrasena: r.contrasena_temporal })
    setFormulario(null)
    recargar()
  }

  async function guardar(cuenta, datos) {
    await api.modificarCuenta(cuenta.id, datos)
    setFormulario(null)
    recargar()
  }

  // Si TI toma el control del acceso de quien firma, deja de firmar
  const yaNoFirma = (c) =>
    c.firma_reportes ? ' Dejará de firmar reportes hasta que otra Responsable de RRHH le devuelva el permiso.' : ''

  // TI no ve datos: lo que le da acceso a una cuenta con datos lo aprueba RRHH
  const enEspera = (c) =>
    c.rol === 'admin_ti' ? '' : ' Su acceso quedará en espera hasta que una Responsable de RRHH lo apruebe.'

  const restablecer = (c) =>
    accion(async () => {
      const r = await api.restablecerContrasena(c.id)
      setTemporal({ nombre: c.nombre, contrasena: r.contrasena_temporal })
    }, `¿Restablecer la contraseña de ${c.nombre}? Sus sesiones abiertas se cerrarán.${yaNoFirma(c)}${enEspera(c)}`)

  return (
    <div>
      <div className="titulo-pagina">
        <div>
          <h1>Usuarios</h1>
          <p className="texto-secundario">
            {esTi
              ? 'Las cuentas no se borran: se desactivan. Todo cambio queda registrado con tu usuario, y lo que hagas con una cuenta de RRHH le llega como aviso a RRHH.'
              : esResponsable
                ? 'Administración de TI administra las cuentas. Tú decides quién de RRHH puede firmar los reportes.'
                : 'Solo Administración de TI administra las cuentas. Aquí puedes revisar quién hizo cada cambio.'}
          </p>
        </div>
        {esTi && !formulario && (
          <button type="button" className="boton-primario" onClick={() => setFormulario('nueva')}>
            Nueva cuenta
          </button>
        )}
      </div>

      {temporal && (
        <Mensaje tipo="advertencia" titulo={`Contraseña temporal de ${temporal.nombre}`}>
          <p>
            <code className="clave-mfa">{temporal.contrasena}</code>
          </p>
          <p>
            Entrégasela por un medio seguro (en persona o por teléfono, no por correo). Se muestra una sola vez y la
            cambiará al entrar.
          </p>
          <button type="button" className="boton-secundario" onClick={() => setTemporal(null)}>
            Listo, ya la entregué
          </button>
        </Mensaje>
      )}
      {error && <Mensaje>{error}</Mensaje>}

      {formulario && (
        <section className="panel">
          <h2>{formulario === 'nueva' ? 'Nueva cuenta' : `Editar a ${formulario.nombre}`}</h2>
          <FormularioCuenta
            key={formulario === 'nueva' ? 'nueva' : formulario.id}
            nueva={formulario === 'nueva'}
            inicial={
              formulario === 'nueva'
                ? VACIA
                : { ...formulario, area_id: formulario.area_id ?? '' }
            }
            areas={areas}
            alGuardar={(datos) => (formulario === 'nueva' ? crear(datos) : guardar(formulario, datos))}
            alCancelar={() => setFormulario(null)}
          />
        </section>
      )}

      {cuentas.error && <Mensaje>{cuentas.error.message}</Mensaje>}
      {cuentas.datos && (
        <div className="panel tabla-desplazable">
          <table className="tabla" aria-label="Cuentas">
            <thead>
              <tr>
                <th scope="col">Usuario</th>
                <th scope="col">Nombre</th>
                <th scope="col">Rol</th>
                <th scope="col">Estado</th>
                <th scope="col">Dos pasos</th>
                <th scope="col">Último acceso</th>
                {(esTi || esResponsable) && <th scope="col"><span className="oculto-visual">Acciones</span></th>}
              </tr>
            </thead>
            <tbody>
              {cuentas.datos.map((c) => {
                const propia = c.usuario === usuario.usuario
                return (
                  <tr key={c.id} className={c.activo ? undefined : 'fila-inactiva'}>
                    <td>{c.usuario}</td>
                    <td>{c.nombre}</td>
                    <td>
                      {cargoDe(c)}
                      {c.area_id !== null && ` · ${nombreArea(c.area_id)}`}
                    </td>
                    <td>
                      {c.activo ? 'Activa' : 'Desactivada'}
                      {c.bloqueado && ' · Bloqueada'}
                      {c.debe_cambiar_contrasena && ' · Contraseña temporal'}
                      {!c.acceso_aprobado && ' · Espera aprobación'}
                    </td>
                    <td>{c.mfa_activo ? 'Activa' : '—'}</td>
                    <td>{c.ultimo_acceso ? fechaHora(c.ultimo_acceso) : 'Nunca'}</td>
                    {esTi && (
                      <td className="acciones">
                        <button
                          type="button"
                          className="boton-texto"
                          aria-label={`Editar ${c.usuario}`}
                          onClick={() => setFormulario(c)}
                        >
                          Editar
                        </button>
                        {!propia && (
                          <>
                            <button
                              type="button"
                              className="boton-texto"
                              aria-label={`${c.activo ? 'Desactivar' : 'Reactivar'} ${c.usuario}`}
                              onClick={() =>
                                accion(
                                  () => api.modificarCuenta(c.id, { activo: !c.activo }),
                                  c.activo && `¿Desactivar la cuenta de ${c.nombre}? No podrá entrar hasta que la reactives.`,
                                )
                              }
                            >
                              {c.activo ? 'Desactivar' : 'Reactivar'}
                            </button>
                            <button
                              type="button"
                              className="boton-texto"
                              aria-label={`Restablecer contraseña de ${c.usuario}`}
                              onClick={() => restablecer(c)}
                            >
                              Restablecer contraseña
                            </button>
                            {c.mfa_activo && (
                              <button
                                type="button"
                                className="boton-texto"
                                aria-label={`Reiniciar verificación en dos pasos de ${c.usuario}`}
                                onClick={() =>
                                  accion(
                                    () => api.reiniciarMfa(c.id),
                                    `¿Reiniciar la verificación en dos pasos de ${c.nombre}? Deberá configurarla de nuevo al entrar.${yaNoFirma(c)}`,
                                  )
                                }
                              >
                                Reiniciar dos pasos
                              </button>
                            )}
                          </>
                        )}
                      </td>
                    )}
                    {esResponsable && (
                      <td className="acciones">
                        {!c.acceso_aprobado && c.activo && !propia && (
                          <>
                            <button
                              type="button"
                              className="boton-texto"
                              aria-label={`Aprobar el acceso de ${c.usuario}`}
                              onClick={() =>
                                accion(
                                  () => api.aprobarAcceso(c.id, true),
                                  `¿Aprobar el acceso de ${c.nombre}? Confirma antes con esa persona que ella lo pidió y que ya entró: TI lo dejó en espera.`,
                                )
                              }
                            >
                              Aprobar
                            </button>
                            <button
                              type="button"
                              className="boton-texto"
                              aria-label={`Rechazar el acceso de ${c.usuario}`}
                              onClick={() =>
                                accion(
                                  () => api.aprobarAcceso(c.id, false),
                                  `¿Rechazar el acceso de ${c.nombre}? La cuenta se desactivará.`,
                                )
                              }
                            >
                              Rechazar
                            </button>
                          </>
                        )}
                        {c.rol === 'rrhh' && c.activo && !propia && c.acceso_aprobado && (
                          <button
                            type="button"
                            className="boton-texto"
                            aria-label={`${c.firma_reportes ? 'Quitar' : 'Dar'} permiso de firma a ${c.usuario}`}
                            onClick={() =>
                              accion(
                                () => api.cambiarFirma(c.id, !c.firma_reportes),
                                c.firma_reportes
                                  ? `¿Quitar a ${c.nombre} el permiso de firmar reportes?`
                                  : `¿Dar a ${c.nombre} el permiso de firmar reportes? Podrá aprobar los reportes que van a Dirección.`,
                              )
                            }
                          >
                            {c.firma_reportes ? 'Quitar firma' : 'Dar firma'}
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

      <section className="seccion">
        <h2>Inicios de sesión</h2>
        {accesos.error && <Mensaje>{accesos.error.message}</Mensaje>}
        {accesos.datos?.length === 0 && <p className="nota">Todavía no hay inicios de sesión registrados.</p>}
        {accesos.datos?.length > 0 && (
          <div className="panel tabla-desplazable">
            <table className="tabla" aria-label="Inicios de sesión">
              <thead>
                <tr>
                  <th scope="col">Fecha</th>
                  <th scope="col">Cuenta</th>
                  <th scope="col">Qué pasó</th>
                  <th scope="col">Desde</th>
                </tr>
              </thead>
              <tbody>
                {accesos.datos.map((a) => (
                  <tr key={a.id}>
                    <td>{fechaHora(a.momento)}</td>
                    <td>{a.usuario}</td>
                    <td>{a.evento === 'entrada' ? 'Entró' : 'Intento fallido'}</td>
                    <td>{a.origen ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="seccion">
        <h2>Bitácora de cuentas</h2>
        {cambios.error && <Mensaje>{cambios.error.message}</Mensaje>}
        {cambios.datos?.length === 0 && <p className="nota">Todavía no hay cambios registrados.</p>}
        {cambios.datos?.length > 0 && (
          <div className="panel tabla-desplazable">
            <table className="tabla" aria-label="Bitácora de cuentas">
              <thead>
                <tr>
                  <th scope="col">Fecha</th>
                  <th scope="col">Cuenta</th>
                  <th scope="col">Qué pasó</th>
                  <th scope="col">Detalle</th>
                  <th scope="col">Quién</th>
                  <th scope="col">Desde</th>
                </tr>
              </thead>
              <tbody>
                {cambios.datos.map((c) => (
                  <tr key={c.id}>
                    <td>{fechaHora(c.hecho_en)}</td>
                    <td>{c.usuario}</td>
                    <td>{ACCIONES[c.accion] ?? c.accion}</td>
                    <td>{detalle(c, nombreArea) || '—'}</td>
                    <td>{quien(c.hecho_por)}</td>
                    <td>{c.origen ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
