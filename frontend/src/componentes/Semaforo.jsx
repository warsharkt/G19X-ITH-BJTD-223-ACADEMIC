import { infoEstado } from '../formato'

// Insignia del semaforo: icono + texto, nunca solo color.
export default function Semaforo({ estado, pequeno = false }) {
  const { etiqueta, icono, clase } = infoEstado(estado)
  return (
    <span className={`semaforo semaforo-${clase}${pequeno ? ' semaforo-pequeno' : ''}`}>
      <span className="semaforo-icono" aria-hidden="true">
        {icono}
      </span>
      {etiqueta}
    </span>
  )
}
