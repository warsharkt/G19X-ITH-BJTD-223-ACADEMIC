import { Navigate, Route, Routes } from 'react-router-dom'
import Marco from './componentes/Marco'
import Avisos from './paginas/Avisos'
import Configuracion from './paginas/Configuracion'
import DetalleNarrativa from './paginas/DetalleNarrativa'
import Login from './paginas/Login'
import Narrativas from './paginas/Narrativas'
import Tablero from './paginas/Tablero'
import { puedeVerDatos, useSesion } from './sesion'

export default function App() {
  const { usuario, cargando } = useSesion()
  if (cargando) return <p className="cargando">Cargando…</p>
  if (!usuario) return <Login />

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
        <Route path="*" element={<Navigate to={inicio} replace />} />
      </Route>
    </Routes>
  )
}
