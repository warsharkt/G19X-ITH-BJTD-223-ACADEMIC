import { useState } from 'react'
import { api } from '../api'
import Mensaje from '../componentes/Mensaje'
import { fechaHora } from '../formato'
import { NOMBRES_ROL, useSesion } from '../sesion'
import { useConsulta } from '../useConsulta'

const ACCIONES = {
  crear: 'Creó la cuenta',
  modificar: 'Modificó la cuenta',
  desactivar: 'Desactivó la cuenta',
  reactivar: 'Reactivó la cuenta',
  restablecer_contrasena: 'Restableció la contraseña',
  cambiar_contrasena: 'Cambió su contraseña',
  activar_mfa: 'Activó la verificación en dos pasos',
  reiniciar_mfa: 'Reinició la verificación en dos pasos',
  usar_codigo_respaldo: 'Entró con un código de respaldo',
}
const CAMPOS = { nombre: 'nombre', rol: 'rol', area_id: 'área', correo: 'correo', activo: 'activa' }
const VACIA = { usuario: '', nombre: '', rol: 'gerente', area_id: '', correo: '' }

// Detalle de la bitacora en palabras: "rol: Gerencia de área → Recursos Humanos"
function detalle(c, nombreArea) {
  const valor = (campo, v) => {
    if (v === null || v === undefined || v === '') return '—'
    if (campo === 'rol') return NOMBRES_ROL[v] ?? v
    if (campo === 'area_id') return nombreArea(v)
    if (campo === 'activo') return v ? 'sí' : 'no'
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
            {Object.entries(NOMBRES_ROL).map(([rol, nombre]) => (
              <option key={rol} value={rol}>
                {nombre}
              </option>
            ))}
          </select>
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
  const [version, setVersion] = useState(0)
  const cuentas = useConsulta(() => api.cuentas(), [version])
  const cambios = useConsulta(() => api.cambiosCuentas(), [version])
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

  const restablecer = (c) =>
    accion(async () => {
      const r = await api.restablecerContrasena(c.id)
      setTemporal({ nombre: c.nombre, contrasena: r.contrasena_temporal })
    }, `¿Restablecer la contraseña de ${c.nombre}? Sus sesiones abiertas se cerrarán.`)

  return (
    <div>
      <div className="titulo-pagina">
        <div>
          <h1>Usuarios</h1>
          <p className="texto-secundario">
            {esTi
              ? 'Las cuentas no se borran: se desactivan. Todo cambio queda registrado con tu usuario.'
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
            inicial={formulario === 'nueva' ? VACIA : { ...formulario, area_id: formulario.area_id ?? '' }}
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
                {esTi && <th scope="col"><span className="oculto-visual">Acciones</span></th>}
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
                      {NOMBRES_ROL[c.rol] ?? c.rol}
                      {c.area_id !== null && ` · ${nombreArea(c.area_id)}`}
                    </td>
                    <td>
                      {c.activo ? 'Activa' : 'Desactivada'}
                      {c.bloqueado && ' · Bloqueada'}
                      {c.debe_cambiar_contrasena && ' · Contraseña temporal'}
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
                                    `¿Reiniciar la verificación en dos pasos de ${c.nombre}? Deberá configurarla de nuevo al entrar.`,
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
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

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
                </tr>
              </thead>
              <tbody>
                {cambios.datos.map((c) => (
                  <tr key={c.id}>
                    <td>{fechaHora(c.hecho_en)}</td>
                    <td>{c.usuario}</td>
                    <td>{ACCIONES[c.accion] ?? c.accion}</td>
                    <td>{detalle(c, nombreArea) || '—'}</td>
                    <td>{c.hecho_por}</td>
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
