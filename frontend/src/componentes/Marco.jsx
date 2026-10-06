import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { api, AVISOS_CAMBIARON } from '../api'
import { NOMBRES_ROL, puedeCargarDatos, puedeVerCuentas, puedeVerDatos, useSesion } from '../sesion'
import Icono from './Iconos'
import Marca from './Marca'

export const SEGUNDOS_ENTRE_AVISOS = 60

// Enlace a los avisos con cuantos faltan por leer. Se actualiza cada minuto,
// al cambiar de pagina y cuando la pagina de avisos marca alguno como leido.
function EnlaceAvisos() {
  const { pathname } = useLocation()
  const [noLeidos, setNoLeidos] = useState(0)

  useEffect(() => {
    let vigente = true
    const consultar = () =>
      api
        .avisos({ limite: 1 })
        .then((r) => vigente && setNoLeidos(r.no_leidos))
        .catch(() => {}) // el contador no es critico: la pagina de avisos muestra el error
    consultar()
    const reloj = setInterval(consultar, SEGUNDOS_ENTRE_AVISOS * 1000)
    window.addEventListener(AVISOS_CAMBIARON, consultar)
    return () => {
      vigente = false
      clearInterval(reloj)
      window.removeEventListener(AVISOS_CAMBIARON, consultar)
    }
  }, [pathname])

  return (
    <NavLink to="/avisos">
      <Icono nombre="avisos" />
      Avisos
      {noLeidos > 0 && (
        <>
          <span className="insignia" aria-hidden="true">
            {noLeidos}
          </span>
          <span className="oculto-visual">, {noLeidos} sin leer</span>
        </>
      )}
    </NavLink>
  )
}

const iniciales = (nombre) =>
  nombre
    .split(/\s+/)
    .filter((p) => /^[A-Za-zÁÉÍÓÚÑáéíóúñ]/.test(p))
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join('')

// Estructura comun de las paginas con sesion: menu lateral, encabezado y contenido.
export default function Marco() {
  const { usuario, marca, cerrarSesion } = useSesion()
  const conDatos = puedeVerDatos(usuario)
  return (
    <div className="marco">
      <aside className="lateral">
        <Marca />
        <nav className="menu" aria-label="Secciones">
          {conDatos && (
            <NavLink to="/tablero">
              <Icono nombre="tablero" />
              Tablero
            </NavLink>
          )}
          {conDatos && (
            <NavLink to="/narrativas">
              <Icono nombre="narrativas" />
              Narrativas
            </NavLink>
          )}
          {/* TI no recibe avisos: todos hablan de datos de colaboradores */}
          {conDatos && <EnlaceAvisos />}
          {puedeCargarDatos(usuario) && (
            <NavLink to="/carga">
              <Icono nombre="carga" />
              Carga de datos
            </NavLink>
          )}
          <NavLink to="/configuracion">
            <Icono nombre="configuracion" />
            Configuración
          </NavLink>
          {puedeVerCuentas(usuario) && (
            <NavLink to="/usuarios">
              <Icono nombre="usuarios" />
              Usuarios
            </NavLink>
          )}
        </nav>
        {marca.empresa && (
          <div className="empresa-lateral">
            <span>Empresa</span>
            <strong>{marca.empresa}</strong>
          </div>
        )}
      </aside>
      <div className="area-principal">
        <header className="encabezado">
          <div className="encabezado-interior">
            <span className="encabezado-seguridad">
              <Icono nombre="escudo" tamano={16} />
              {usuario.mfa_activo ? 'Sesión verificada en dos pasos' : 'Sesión protegida'} · acceso por rol
            </span>
            <div className="cuenta">
              <NavLink to="/cuenta" className="cuenta-enlace" title="Mi cuenta">
                <span className="cuenta-nombre">
                  {usuario.nombre}
                  <span className="cuenta-rol">{NOMBRES_ROL[usuario.rol] ?? usuario.rol}</span>
                </span>
                <span className="avatar" aria-hidden="true">
                  {iniciales(usuario.nombre)}
                </span>
              </NavLink>
              <button type="button" className="boton-secundario" onClick={() => cerrarSesion()}>
                Cerrar sesión
              </button>
            </div>
          </div>
        </header>
        <main className="contenido">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
