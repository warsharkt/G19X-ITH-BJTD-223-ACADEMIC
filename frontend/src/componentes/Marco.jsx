import { NavLink, Outlet } from 'react-router-dom'
import { NOMBRES_ROL, puedeVerDatos, useSesion } from '../sesion'

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
            <NavLink to="/umbrales">Umbrales</NavLink>
          </nav>
          <div className="cuenta">
            <span className="cuenta-nombre">
              {usuario.nombre}
              <span className="cuenta-rol">{NOMBRES_ROL[usuario.rol] ?? usuario.rol}</span>
            </span>
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
