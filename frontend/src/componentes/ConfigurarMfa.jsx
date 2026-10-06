import { useState } from 'react'
import { api } from '../api'
import { useSesion } from '../sesion'
import TelefonoSimulado from './TelefonoSimulado'
import Mensaje from './Mensaje'

// Entrega los codigos de respaldo como archivo de texto
function descargarCodigos(codigos) {
  const blob = new Blob([`Códigos de respaldo de Talentia Insights\n\n${codigos.join('\n')}\n`], {
    type: 'text/plain',
  })
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = 'codigos-de-respaldo.txt'
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

// Verificacion en dos pasos en tres pasos: QR, codigo de prueba y codigos de
// respaldo (se muestran una sola vez).
export default function ConfigurarMfa({ alTerminar }) {
  const { demo, usuario } = useSesion()
  const [qr, setQr] = useState(null) // { secreto, qr }
  const [codigo, setCodigo] = useState('')
  const [respaldo, setRespaldo] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState(null)

  async function generar() {
    setError(null)
    setEnviando(true)
    try {
      setQr(await api.configurarMfa())
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  async function activar(e) {
    e.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      setRespaldo((await api.activarMfa(codigo.trim())).codigos)
    } catch (err) {
      setError(err.message)
      setCodigo('')
    } finally {
      setEnviando(false)
    }
  }

  if (respaldo)
    return (
      <div className="formulario-columna">
        <Mensaje tipo="exito" titulo="Verificación en dos pasos activada" />
        <p>
          Guarda estos <strong>códigos de respaldo</strong> en un lugar seguro. Si no tienes tu teléfono, cada uno sirve
          para entrar <strong>una sola vez</strong>. No se vuelven a mostrar.
        </p>
        <ul className="codigos-respaldo" aria-label="Códigos de respaldo">
          {respaldo.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <div className="botones">
          <button type="button" className="boton-secundario" onClick={() => descargarCodigos(respaldo)}>
            Descargar códigos
          </button>
          <button type="button" className="boton-primario" onClick={alTerminar}>
            Ya los guardé
          </button>
        </div>
      </div>
    )

  return (
    <div className="formulario-columna">
      {error && <Mensaje>{error}</Mensaje>}
      {!qr ? (
        <>
          <p>
            Necesitas una app de autenticación en tu teléfono, por ejemplo Google Authenticator o Microsoft
            Authenticator. Cada vez que entres, además de tu contraseña, escribirás el código que te muestre.
          </p>
          <button type="button" className="boton-primario" disabled={enviando} onClick={generar}>
            {enviando ? 'Generando…' : 'Generar código QR'}
          </button>
        </>
      ) : (
        <div className={demo.activo ? 'configurar-con-telefono' : undefined}>
          <form className="formulario-columna" onSubmit={activar}>
            <p>1. Escanea este código con tu app.</p>
            <img className="qr-mfa" src={qr.qr} alt="Código QR para tu app de autenticación" width="200" height="200" />
            <p className="nota">
              ¿No puedes escanearlo? Escribe esta clave en la app: <code className="clave-mfa">{qr.secreto}</code>
            </p>
            <label>
              2. Escribe el código de 6 dígitos que muestra la app
              <input
                autoComplete="one-time-code"
                inputMode="numeric"
                value={codigo}
                onChange={(e) => setCodigo(e.target.value)}
                maxLength={6}
                required
              />
            </label>
            <button type="submit" className="boton-primario" disabled={enviando}>
              {enviando ? 'Activando…' : 'Activar'}
            </button>
          </form>
          {demo.activo && <TelefonoSimulado usuario={usuario.usuario} enTarjeta />}
        </div>
      )}
    </div>
  )
}
