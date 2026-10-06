// Iconos de linea (estilo uniforme). Siempre decorativos: el texto de al lado
// dice lo mismo, asi que van con aria-hidden.
const RUTAS = {
  tablero: 'M4 13h4v7H4zM10 4h4v16h-4zM16 9h4v11h-4z',
  narrativas: 'M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6',
  avisos: 'M18 16V11a6 6 0 1 0-12 0v5l-2 2h16zM10 20a2 2 0 0 0 4 0',
  carga: 'M12 15V4M7 9l5-5 5 5M5 15v4h14v-4',
  configuracion: 'M4 7h10M18 7h2M4 17h4M12 17h8M14 5v4M8 15v4',
  usuarios: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 4.5a3.5 3.5 0 0 1 0 6.5M18 14c2 .7 3 2.8 3 6',
  escudo: 'M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6zM9 12l2 2 4-4',
  candado: 'M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3',
  telefono: 'M8 3h8a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM11 18h2',
  bitacora: 'M5 4h11l3 3v13H5zM8 9h8M8 13h8M8 17h5',
  huella: 'M12 11v3M8.5 16.5c.6-1.4 1-3 1-4.5a2.5 2.5 0 0 1 5 0c0 2-.3 3.8-.9 5.4M6 14c.3-1 .5-2 .5-3a5.5 5.5 0 0 1 11 0c0 1.2-.1 2.4-.3 3.5M17 18.5c.3-.9.6-1.9.8-3',
  ia: 'M12 3v3M12 18v3M3 12h3M18 12h3M7 7l2 2M15 15l2 2M17 7l-2 2M9 15l-2 2M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
  descargar: 'M12 4v11M7 10l5 5 5-5M5 19h14',
  archivo: 'M7 3h7l5 5v13H7zM14 3v5h5',
  ojo_cerrado: 'M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.2A9 9 0 0 1 21 12c-.6 1.2-1.4 2.3-2.4 3.2M6.3 6.3A9.4 9.4 0 0 0 3 12c1.7 3.6 5 6 9 6 1.5 0 2.9-.3 4.1-.9',
  todo_o_nada: 'M4 12l5 5L20 6',
  salir: 'M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10',
}

export default function Icono({ nombre, tamano = 18 }) {
  return (
    <svg
      width={tamano}
      height={tamano}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={RUTAS[nombre]} />
    </svg>
  )
}
