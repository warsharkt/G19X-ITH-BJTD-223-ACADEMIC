import { useState } from 'react'
import { api, guardarToken } from '../api'
import Mensaje from './Mensaje'

const LONGITUD_MINIMA = 10

// Cambio de contrasena de la propia persona. La API cierra sus otras sesiones
// y devuelve un token nuevo para esta.
export default function FormularioContrasena({ alCambiar, textoBoton = 'Cambiar contraseña' }) {
  const [campos, setCampos] = useState({ actual: '', nueva: '', repetida: '' })
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState(null)

  const cambio = (campo) => (e) => setCampos({ ...campos, [campo]: e.target.value })

  async function enviar(e) {
    e.preventDefault()
    setError(null)
    if (campos.nueva.length < LONGITUD_MINIMA) {
      setError(`La contraseña nueva debe tener al menos ${LONGITUD_MINIMA} caracteres`)
      return
    }
    if (campos.nueva !== campos.repetida) {
      setError('Las contraseñas nuevas no coinciden')
      return
    }
    setEnviando(true)
    try {
      const { access_token } = await api.cambiarContrasena(campos.actual, campos.nueva)
      guardarToken(access_token)
      setCampos({ actual: '', nueva: '', repetida: '' })
      await alCambiar()
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form className="formulario-columna" onSubmit={enviar}>
      {error && <Mensaje>{error}</Mensaje>}
      <label>
        Contraseña actual
        <input type="password" autoComplete="current-password" value={campos.actual} onChange={cambio('actual')} required />
      </label>
      <label>
        Contraseña nueva
        <input type="password" autoComplete="new-password" value={campos.nueva} onChange={cambio('nueva')} required />
      </label>
      <label>
        Repite la contraseña nueva
        <input type="password" autoComplete="new-password" value={campos.repetida} onChange={cambio('repetida')} required />
      </label>
      <p className="nota">Mínimo {LONGITUD_MINIMA} caracteres y sin tu nombre de usuario.</p>
      <button type="submit" className="boton-primario" disabled={enviando}>
        {enviando ? 'Guardando…' : textoBoton}
      </button>
    </form>
  )
}
