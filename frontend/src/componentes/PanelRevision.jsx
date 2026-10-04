import { useState } from 'react'
import { api } from '../api'
import { fechaHora } from '../formato'
import { useSesion } from '../sesion'
import Mensaje from './Mensaje'

// Revision humana del reporte (RF-05). Las reglas las aplica la API: solo
// RRHH revisa, nunca lo que la misma persona solicito, y la decision es
// definitiva. Aqui solo se muestran los botones a quien puede usarlos.
export default function PanelRevision({ trabajo, alRevisar }) {
  const { usuario } = useSesion()
  const [comentario, setComentario] = useState('')
  const [enviando, setEnviando] = useState(null) // decision en curso
  const [error, setError] = useState(null)

  if (trabajo.revision === 'aprobada')
    return (
      <div className="mensaje mensaje-exito" role="note">
        <strong>
          Aprobado por {trabajo.revisada_por} el {fechaHora(trabajo.revisada_en)}
        </strong>
        {trabajo.comentario_revision && <span>Comentario: {trabajo.comentario_revision}</span>}
        <span>Este reporte ya se puede distribuir.</span>
      </div>
    )

  if (trabajo.revision === 'rechazada')
    return (
      <div className="mensaje mensaje-error" role="note">
        <strong>
          Rechazado por {trabajo.revisada_por} el {fechaHora(trabajo.revisada_en)}
        </strong>
        <span>Motivo: {trabajo.comentario_revision}</span>
        <span>No se debe distribuir. Si hace falta, solicita un reporte nuevo.</span>
      </div>
    )

  const puedeRevisar = usuario.rol === 'rrhh' && usuario.usuario !== trabajo.solicitada_por

  async function decidir(decision) {
    setError(null)
    setEnviando(decision)
    try {
      alRevisar(await api.revisar(trabajo.id, decision, comentario))
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(null)
    }
  }

  return (
    <div className="mensaje mensaje-advertencia panel-revision" role="note">
      <strong>Borrador pendiente de revisión.</strong>
      <span>
        Lo redactó un modelo de IA a partir de los indicadores calculados. Una persona de RRHH debe aprobarlo antes
        de distribuirlo.
      </span>
      {usuario.rol === 'rrhh' && !puedeRevisar && (
        <span className="nota">Tú lo solicitaste: debe revisarlo otra persona de RRHH.</span>
      )}
      {puedeRevisar && (
        <form className="formulario-revision" onSubmit={(e) => e.preventDefault()}>
          <label>
            Comentario (obligatorio si lo rechazas)
            <textarea
              value={comentario}
              onChange={(e) => setComentario(e.target.value)}
              maxLength={1000}
              rows={2}
              placeholder="Qué revisaste o qué hay que corregir"
            />
          </label>
          {error && <Mensaje>{error}</Mensaje>}
          <div className="botones">
            <button type="button" className="boton-primario" disabled={enviando} onClick={() => decidir('aprobada')}>
              {enviando === 'aprobada' ? 'Aprobando…' : 'Aprobar'}
            </button>
            <button
              type="button"
              className="boton-secundario boton-peligro"
              disabled={enviando}
              onClick={() => decidir('rechazada')}
            >
              {enviando === 'rechazada' ? 'Rechazando…' : 'Rechazar'}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
