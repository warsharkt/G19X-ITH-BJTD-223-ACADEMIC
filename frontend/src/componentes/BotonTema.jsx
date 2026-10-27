import { useState } from 'react'
import { guardarTema, temaActual } from '../tema'
import Icono from './Iconos'

// Cambia entre el diseno claro (blanco) y el oscuro. El icono muestra el
// diseno al que se va a cambiar.
export default function BotonTema() {
  const [tema, setTema] = useState(temaActual)
  const siguiente = tema === 'oscuro' ? 'claro' : 'oscuro'

  const cambiar = () => {
    guardarTema(siguiente)
    setTema(siguiente)
  }

  return (
    <button
      type="button"
      className="boton-tema"
      onClick={cambiar}
      aria-label={`Cambiar a diseño ${siguiente}`}
      title={`Cambiar a diseño ${siguiente}`}
    >
      <Icono nombre={siguiente === 'oscuro' ? 'luna' : 'sol'} />
    </button>
  )
}
