import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ProveedorSesion } from './sesion'
import { aplicarTema, temaInicial } from './tema'
// La fuente se sirve desde el propio tablero (antes Google Fonts): el
// navegador no le avisa a un tercero cada vez que alguien abre el sistema, y
// funciona en una red sin internet. Solo el alfabeto latino (incluye acentos y ñ).
import '@fontsource/inter/latin-400.css'
import '@fontsource/inter/latin-500.css'
import '@fontsource/inter/latin-600.css'
import '@fontsource/inter/latin-700.css'
import '@fontsource/inter/latin-800.css'
import './estilos.css'

aplicarTema(temaInicial())

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <ProveedorSesion>
        <App />
      </ProveedorSesion>
    </BrowserRouter>
  </StrictMode>,
)
