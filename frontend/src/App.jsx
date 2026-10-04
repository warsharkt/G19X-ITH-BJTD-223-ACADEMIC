import { Navigate, Route, Routes } from 'react-router-dom'
import Marco from './componentes/Marco'
import DetalleNarrativa from './paginas/DetalleNarrativa'
import Login from './paginas/Login'
import Narrativas from './paginas/Narrativas'
import Tablero from './paginas/Tablero'
import Umbrales from './paginas/Umbrales'
import { puedeVerDatos, useSesion } from './sesion'

export default function App() {
  const { usuario, cargando } = useSesion()
  if (cargando) return <p className="cargando">Cargando…</p>
  if (!usuario) return <Login />

  const conDatos = puedeVerDatos(usuario)
  const inicio = conDatos ? '/tablero' : '/umbrales'
  return (
    <Routes>
      <Route element={<Marco />}>
        {conDatos && <Route path="/tablero" element={<Tablero />} />}
        {conDatos && <Route path="/narrativas" element={<Narrativas />} />}
        {conDatos && <Route path="/narrativas/:id" element={<DetalleNarrativa />} />}
        <Route path="/umbrales" element={<Umbrales />} />
        <Route path="*" element={<Navigate to={inicio} replace />} />
      </Route>
    </Routes>
  )
}
