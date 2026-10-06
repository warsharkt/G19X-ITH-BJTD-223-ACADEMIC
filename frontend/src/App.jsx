import { Navigate, Route, Routes } from 'react-router-dom'
import Marco from './componentes/Marco'
import Avisos from './paginas/Avisos'
import Configuracion from './paginas/Configuracion'
import Cuenta from './paginas/Cuenta'
import DetalleNarrativa from './paginas/DetalleNarrativa'
import Login from './paginas/Login'
import Narrativas from './paginas/Narrativas'
import Pendiente from './paginas/Pendiente'
import Tablero from './paginas/Tablero'
import Usuarios from './paginas/Usuarios'
import { puedeVerCuentas, puedeVerDatos, useSesion } from './sesion'

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
        <Route path="/configuracion" element={<Configuracion />} />
        {puedeVerCuentas(usuario) && <Route path="/usuarios" element={<Usuarios />} />}
        <Route path="/cuenta" element={<Cuenta />} />
        <Route path="*" element={<Navigate to={inicio} replace />} />
      </Route>
    </Routes>
  )
}
