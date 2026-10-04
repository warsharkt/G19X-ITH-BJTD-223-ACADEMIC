// Aviso en pantalla: error de la API, informacion o advertencia.
export default function Mensaje({ tipo = 'error', titulo, children }) {
  return (
    <div className={`mensaje mensaje-${tipo}`} role={tipo === 'error' ? 'alert' : 'status'}>
      {titulo && <strong>{titulo}</strong>}
      {children && <div>{children}</div>}
    </div>
  )
}
