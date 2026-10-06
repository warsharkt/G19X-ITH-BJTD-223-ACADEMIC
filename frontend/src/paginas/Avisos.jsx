import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, AVISOS_CAMBIARON } from '../api'
import Mensaje from '../componentes/Mensaje'
import { fechaHora } from '../formato'
import { useConsulta } from '../useConsulta'

// Cada tipo con icono y texto, nunca solo color (como el semaforo)
const TIPOS = {
  alerta: { texto: 'Alerta', clase: 'rojo', icono: '▲' },
  revision: { texto: 'Por revisar', clase: 'amarillo', icono: '●' },
  aprobado: { texto: 'Aprobado', clase: 'verde', icono: '✓' },
  rechazado: { texto: 'Rechazado', clase: 'neutro', icono: '✕' },
  error: { texto: 'Error', clase: 'rojo', icono: '✕' },
}

const avisarCambio = () => window.dispatchEvent(new Event(AVISOS_CAMBIARON))

// Avisos de la persona (RF-09): alertas en rojo, reportes por revisar,
// aprobados o rechazados. Cada uno lleva a donde se atiende. El correo, si
// esta activo, solo dice que hay avisos nuevos y trae aqui.
export default function Avisos() {
  const [version, setVersion] = useState(0)
  const avisos = useConsulta(() => api.avisos({ limite: 100 }), [version])
  const [marcando, setMarcando] = useState(false)
  const [error, setError] = useState(null)

  // Al abrir un aviso se marca como leido; la navegacion no espera a la API
  function abrir(aviso) {
    if (aviso.leido_en) return
    api.marcarAvisoLeido(aviso.id).then(avisarCambio, () => {})
  }

  async function marcarTodos() {
    setError(null)
    setMarcando(true)
    try {
      await api.marcarAvisosLeidos()
      setVersion((v) => v + 1)
      avisarCambio()
    } catch (err) {
      setError(err.message)
    } finally {
      setMarcando(false)
    }
  }

  const datos = avisos.datos
  return (
    <div>
      <div className="titulo-pagina">
        <div>
          <h1>Avisos</h1>
          <p className="texto-secundario">
            Indicadores en rojo, reportes por revisar y reportes aprobados o rechazados de las áreas que puedes ver.
          </p>
        </div>
        {datos?.no_leidos > 0 && (
          <button type="button" className="boton-secundario" disabled={marcando} onClick={marcarTodos}>
            {marcando ? 'Marcando…' : 'Marcar todos como leídos'}
          </button>
        )}
      </div>
      {(avisos.error || error) && <Mensaje>{error ?? avisos.error.message}</Mensaje>}
      {datos && datos.avisos.length === 0 && <Mensaje tipo="info">No tienes avisos.</Mensaje>}
      {datos && datos.avisos.length > 0 && (
        <ul className="lista-avisos" aria-label="Avisos">
          {datos.avisos.map((a) => {
            const t = TIPOS[a.tipo] ?? { texto: a.tipo, clase: 'neutro', icono: '•' }
            return (
              <li key={a.id} className={a.leido_en ? 'aviso' : 'aviso aviso-nuevo'}>
                <span className={`semaforo semaforo-${t.clase} semaforo-pequeno`}>
                  <span className="semaforo-icono" aria-hidden="true">
                    {t.icono}
                  </span>
                  {t.texto}
                </span>
                <Link to={a.enlace} onClick={() => abrir(a)} className="aviso-titulo">
                  {a.titulo}
                </Link>
                <span className="nota">
                  {!a.leido_en && <strong className="aviso-marca">Nuevo · </strong>}
                  {fechaHora(a.creado_en)}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
