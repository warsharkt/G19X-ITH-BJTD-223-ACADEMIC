import { lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Marco from './componentes/Marco'
import Login from './paginas/Login'
import Pendiente from './paginas/Pendiente'
import { puedeCargarDatos, puedeVerCuentas, puedeVerDatos, useSesion } from './sesion'

// Cada pantalla se descarga al abrirla: el inicio de sesion ya no baja las
// graficas (Recharts) ni las demas pantallas. Marco muestra "Cargando…" mientras.
const Avisos = lazy(() => import('./paginas/Avisos'))
const CargaDatos = lazy(() => import('./paginas/CargaDatos'))
const Configuracion = lazy(() => import('./paginas/Configuracion'))
const Cuenta = lazy(() => import('./paginas/Cuenta'))
const DetalleNarrativa = lazy(() => import('./paginas/DetalleNarrativa'))
const Narrativas = lazy(() => import('./paginas/Narrativas'))
const Tablero = lazy(() => import('./paginas/Tablero'))
const Usuarios = lazy(() => import('./paginas/Usuarios'))

export default function App() {
  const { usuario, cargando } = useSesion()
  if (cargando) return <p className="cargando">Cargando…</p>
  if (!usuario) return <Login />
  // Contrasena temporal o MFA por configurar: nada mas hasta resolverlo
  if (usuario.pendiente) return <Pendiente />

  const conDatos = puedeVerDatos(usuario)
  const inicio = conDatos ? '/tablero' : '/configuracion'
  return (
    <Routes>
      <Route element={<Marco />}>
        {conDatos && <Route path="/tablero" element={<Tablero />} />}
        {conDatos && <Route path="/narrativas" element={<Narrativas />} />}
        {conDatos && <Route path="/narrativas/:id" element={<DetalleNarrativa />} />}
        {conDatos && <Route path="/avisos" element={<Avisos />} />}
        {puedeCargarDatos(usuario) && <Route path="/carga" element={<CargaDatos />} />}
        <Route path="/configuracion" element={<Configuracion />} />
        {puedeVerCuentas(usuario) && <Route path="/usuarios" element={<Usuarios />} />}
        <Route path="/cuenta" element={<Cuenta />} />
        <Route path="*" element={<Navigate to={inicio} replace />} />
      </Route>
    </Routes>
  )
}
