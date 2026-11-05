import { Component } from 'react'
import Mensaje from './Mensaje'

// Si una pantalla no se puede abrir, el aviso sale en su lugar y el menu sigue
// funcionando; sin esto React deja la pagina en blanco. Pasa sobre todo con una
// pestana abierta durante una actualizacion: las pantallas se descargan al
// abrirlas (lazy en App.jsx) y la version que esa pestana pide ya no existe.
// Marco le pone key={pathname}: al ir a otra pantalla el aviso se quita solo.
export default class LimiteDeError extends Component {
  state = { fallo: false }

  static getDerivedStateFromError() {
    return { fallo: true }
  }

  render() {
    if (!this.state.fallo) return this.props.children
    return (
      <Mensaje titulo="No se pudo abrir esta pantalla">
        <p>Puede que haya una versión nueva del tablero o que se perdiera la conexión.</p>
        <button type="button" className="boton-secundario" onClick={() => window.location.reload()}>
          Recargar
        </button>
      </Mensaje>
    )
  }
}
