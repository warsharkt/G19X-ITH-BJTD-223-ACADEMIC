import { useState } from 'react'
import Mensaje from '../componentes/Mensaje'
import { useSesion } from '../sesion'

// Inicio de sesion en uno o dos pasos: contrasena y, si la cuenta tiene
// verificacion en dos pasos, el codigo de la app (o uno de respaldo).
export default function Login() {
  const { iniciarSesion, verificarMfa, aviso } = useSesion()
  const [usuario, setUsuario] = useState('')
  const [contrasena, setContrasena] = useState('')
  const [mfaToken, setMfaToken] = useState(null) // segundo paso pendiente
  const [codigo, setCodigo] = useState('')
  const [error, setError] = useState(null)
  const [enviando, setEnviando] = useState(false)

  async function enviar(e) {
    e.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      if (mfaToken) {
        await verificarMfa(mfaToken, codigo.trim())
      } else {
        const paso = await iniciarSesion(usuario.trim(), contrasena)
        setContrasena('')
        if (paso) setMfaToken(paso)
      }
    } catch (err) {
      setError(err.message)
      setContrasena('')
      setCodigo('')
      if (mfaToken && err.message.includes('venció')) setMfaToken(null) // volver a la contrasena
    } finally {
      setEnviando(false)
    }
  }

  function volver() {
    setMfaToken(null)
    setCodigo('')
    setError(null)
  }

  return (
    <main className="pagina-login">
      <form className="tarjeta-login" onSubmit={enviar}>
        <img src="/icono.svg" alt="" width="40" height="40" />
        <h1>Motor de Reportes de RRHH</h1>
        <p className="texto-secundario">
          {mfaToken
            ? 'Escribe el código de 6 dígitos de tu app de autenticación.'
            : 'Inicia sesión para ver los indicadores y reportes.'}
        </p>

        {aviso && !error && !mfaToken && <Mensaje tipo="info">{aviso}</Mensaje>}
        {error && <Mensaje>{error}</Mensaje>}

        {mfaToken ? (
          <>
            <label>
              Código de verificación
              <input
                name="codigo"
                autoComplete="one-time-code"
                inputMode="numeric"
                value={codigo}
                onChange={(e) => setCodigo(e.target.value)}
                maxLength={20}
                required
                autoFocus
              />
            </label>
            <button type="submit" className="boton-primario" disabled={enviando}>
              {enviando ? 'Verificando…' : 'Verificar'}
            </button>
            <p className="nota">
              ¿No tienes tu teléfono? Escribe uno de tus códigos de respaldo. Si tampoco los tienes, pide a TI que
              reinicie tu verificación en dos pasos.
            </p>
            <button type="button" className="boton-texto" onClick={volver}>
              Volver
            </button>
          </>
        ) : (
          <>
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
          </>
        )}
      </form>
    </main>
  )
}
