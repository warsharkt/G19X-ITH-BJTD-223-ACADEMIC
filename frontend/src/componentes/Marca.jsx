// Logo de Talentia Insights (el mismo de la pestana del navegador).
export default function Marca({ tamano = 34 }) {
  return (
    <span className="marca">
      <img src="/icono.svg" alt="" width={tamano} height={tamano} />
      <span className="marca-texto">
        <strong>Talentia</strong>
        <span>Insights</span>
      </span>
    </span>
  )
}
