import { useState } from 'react'
import Mensaje from '../componentes/Mensaje'
import { useSesion } from '../sesion'

export default function Login() {
  const { iniciarSesion, aviso } = useSesion()
  const [usuario, setUsuario] = useState('')
  const [contrasena, setContrasena] = useState('')
  const [error, setError] = useState(null)
  const [enviando, setEnviando] = useState(false)

  async function enviar(e) {
    e.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      await iniciarSesion(usuario.trim(), contrasena)
    } catch (err) {
      setError(err.message)
      setContrasena('')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <main className="pagina-login">
      <form className="tarjeta-login" onSubmit={enviar}>
        <img src="/icono.svg" alt="" width="40" height="40" />
        <h1>Motor de Reportes de RRHH</h1>
        <p className="texto-secundario">Inicia sesión para ver los indicadores y reportes.</p>

        {aviso && !error && <Mensaje tipo="info">{aviso}</Mensaje>}
        {error && <Mensaje>{error}</Mensaje>}

        <label>
          Usuario
          <input
            name="usuario"
            autoComplete="username"
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            required
            autoFocus
          />
        </label>
        <label>
          Contraseña
          <input
            name="contrasena"
            type="password"
            autoComplete="current-password"
            value={contrasena}
            onChange={(e) => setContrasena(e.target.value)}
            required
          />
        </label>
        <button type="submit" className="boton-primario" disabled={enviando}>
          {enviando ? 'Entrando…' : 'Entrar'}
        </button>
        <p className="nota">Tras 5 intentos fallidos seguidos la cuenta se bloquea unos minutos.</p>
      </form>
    </main>
  )
}
