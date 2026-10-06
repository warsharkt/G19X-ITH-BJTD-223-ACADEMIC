import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { api, AVISOS_CAMBIARON } from '../api'
import { NOMBRES_ROL, puedeVerCuentas, puedeVerDatos, useSesion } from '../sesion'

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

// Estructura comun de las paginas con sesion: encabezado, menu y contenido.
export default function Marco() {
  const { usuario, cerrarSesion } = useSesion()
  const conDatos = puedeVerDatos(usuario)
  return (
    <div className="marco">
      <header className="encabezado">
        <div className="encabezado-interior">
          <span className="marca">
            <img src="/icono.svg" alt="" width="24" height="24" />
            Motor de Reportes de RRHH
          </span>
          <nav className="menu" aria-label="Secciones">
            {conDatos && <NavLink to="/tablero">Tablero</NavLink>}
            {conDatos && <NavLink to="/narrativas">Narrativas</NavLink>}
            {/* TI no recibe avisos: todos hablan de datos de colaboradores */}
            {conDatos && <EnlaceAvisos />}
            <NavLink to="/configuracion">Configuración</NavLink>
            {puedeVerCuentas(usuario) && <NavLink to="/usuarios">Usuarios</NavLink>}
          </nav>
          <div className="cuenta">
            <NavLink to="/cuenta" className="cuenta-nombre" title="Mi cuenta">
              {usuario.nombre}
              <span className="cuenta-rol">{NOMBRES_ROL[usuario.rol] ?? usuario.rol}</span>
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
  )
}
