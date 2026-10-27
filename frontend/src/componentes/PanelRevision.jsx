import { useState } from 'react'
import { api } from '../api'
import { guardarArchivo } from '../archivos'
import { fechaHora } from '../formato'
import { useSesion } from '../sesion'
import Mensaje from './Mensaje'

// Descargas del reporte aprobado (RF-08). La API vuelve a exigir que este
// aprobado y registra quien descargo cada archivo.
function Descargas({ trabajo }) {
  const [enCurso, setEnCurso] = useState(null) // formato que se esta descargando
  const [error, setError] = useState(null)

  async function descargar(formato) {
    setError(null)
    setEnCurso(formato)
    try {
      const { blob, nombre } = await api.exportar(trabajo.id, formato)
      guardarArchivo(blob, nombre ?? `reporte-${trabajo.id}.${formato}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setEnCurso(null)
    }
  }

  return (
    <>
      <div className="botones">
        <button type="button" className="boton-primario" disabled={enCurso} onClick={() => descargar('pdf')}>
          {enCurso === 'pdf' ? 'Preparando PDF…' : 'Descargar PDF'}
        </button>
        <button type="button" className="boton-secundario" disabled={enCurso} onClick={() => descargar('pptx')}>
          {enCurso === 'pptx' ? 'Preparando presentación…' : 'Descargar presentación'}
        </button>
      </div>
      {error && <Mensaje>{error}</Mensaje>}
    </>
  )
}

// Nombre y cargo de quien firma, p. ej. "Ana Ríos (Responsable de RRHH)"
const quien = (firma) => (firma ? `${firma.nombre} (${firma.cargo})` : 'la Responsable de RRHH')

// Contexto que agrego quien firmo: va aparte y firmado, nunca mezclado con la IA
function NotaRrhh({ trabajo }) {
  if (!trabajo.nota_rrhh) return null
  return (
    <aside className="nota-rrhh" aria-label="Nota de RRHH">
      <strong>Nota de RRHH{trabajo.firma && ` · ${trabajo.firma.nombre}`}</strong>
      <p>{trabajo.nota_rrhh}</p>
      <span className="nota">Escrita por quien firmó el reporte; no la redactó la IA.</span>
    </aside>
  )
}

// Firma del reporte (RF-05, regla 10.3.9). Las reglas las aplica la API:
// firma la Responsable de RRHH o su suplente, nunca quien lo solicito, y la
// decision es definitiva. Aqui solo se muestran los botones a quien firma, y
// a los demas a quien se le mando.
export default function PanelRevision({ trabajo, alRevisar }) {
  const { usuario } = useSesion()
  const [comentario, setComentario] = useState('')
  const [nota, setNota] = useState('')
  const [enviando, setEnviando] = useState(null) // decision en curso
  const [error, setError] = useState(null)

  if (trabajo.revision === 'aprobada')
    return (
      <>
        <div className="mensaje mensaje-exito" role="note">
          <strong>
            Firmado por {quien(trabajo.firma)} el {fechaHora(trabajo.revisada_en)}
          </strong>
          {trabajo.comentario_revision && <span>Comentario: {trabajo.comentario_revision}</span>}
          <span>Este reporte ya se puede distribuir.</span>
          <Descargas trabajo={trabajo} />
        </div>
        <NotaRrhh trabajo={trabajo} />
      </>
    )

  if (trabajo.revision === 'rechazada')
    return (
      <div className="mensaje mensaje-error" role="note">
        <strong>
          Rechazado por {quien(trabajo.firma)} el {fechaHora(trabajo.revisada_en)}
        </strong>
        <span>Motivo: {trabajo.comentario_revision}</span>
        <span>No se debe distribuir. Si hace falta, se prepara un reporte nuevo.</span>
      </div>
    )

  const lopidio = usuario.usuario === trabajo.solicitada_por
  const puedeFirmar =
    usuario.rol === 'rrhh' &&
    !lopidio &&
    (usuario.firma_reportes || trabajo.firma?.usuario === usuario.usuario)

  async function decidir(decision) {
    setError(null)
    setEnviando(decision)
    try {
      alRevisar(await api.revisar(trabajo.id, decision, comentario, decision === 'aprobada' ? nota : null))
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(null)
    }
  }

  return (
    <div className="mensaje mensaje-advertencia panel-revision" role="note">
      <strong>{puedeFirmar ? 'Este reporte espera tu firma.' : `Pendiente de firma de ${quien(trabajo.firma)}.`}</strong>
      <span>
        Lo redactó un modelo de IA a partir de los indicadores calculados. Se distribuye solo cuando lo firma la
        Responsable de RRHH; después se podrá descargar en PDF y como presentación.
      </span>
      {lopidio && trabajo.firma && (
        <span className="nota">Tú lo preparaste: se envió a {quien(trabajo.firma)} para su firma.</span>
      )}
      {!trabajo.firma && (
        <span className="nota">
          No hay nadie disponible para firmarlo: TI debe asignar una Responsable de RRHH, o la Responsable debe
          designar una suplente.
        </span>
      )}
      {puedeFirmar && (
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
          <label>
            Nota de RRHH (opcional, solo al aprobar)
            <textarea
              value={nota}
              onChange={(e) => setNota(e.target.value)}
              maxLength={600}
              rows={2}
              placeholder="Contexto para Dirección, p. ej. una causa ya conocida. Va firmada y aparte del texto de la IA."
            />
          </label>
          {error && <Mensaje>{error}</Mensaje>}
          <div className="botones">
            <button type="button" className="boton-primario" disabled={enviando} onClick={() => decidir('aprobada')}>
              {enviando === 'aprobada' ? 'Firmando…' : 'Aprobar y firmar'}
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
