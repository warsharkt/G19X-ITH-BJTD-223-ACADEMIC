import { fechaHora, nombreMes } from '../formato'
import Semaforo from './Semaforo'

const CONFIANZA = { alta: 'Confianza alta', media: 'Confianza media', baja: 'Confianza baja' }

function Confianza({ nivel }) {
  return <span className={`confianza confianza-${nivel}`}>{CONFIANZA[nivel] ?? nivel}</span>
}

// Hechos (indicadores) que respaldan un hallazgo o una recomendacion
function Respaldo({ ids, hechos, fuentes }) {
  return (
    <p className="respaldo">
      <span className="respaldo-titulo">Respaldo:</span>{' '}
      {ids.map((id) => {
        const h = hechos[id]
        return (
          <span key={id} className="hecho-cita" title={h?.situacion}>
            {h ? `${h.nombre}: ${h.valor_texto}` : id}
          </span>
        )
      })}
      <span className="respaldo-fuente">Fuente: {fuentes.join(', ')}</span>
    </p>
  )
}

// Reporte ejecutivo (seccion 10.1 del PRD) a partir de la respuesta de la API.
// `aviso`: estado de la revision humana, bajo la portada.
export default function VistaNarrativa({ narrativa: n, aviso }) {
  const hechos = Object.fromEntries(n.hechos.map((h) => [h.id, h]))
  const alertas = n.hechos.filter((h) => h.estado === 'rojo' || h.estado === 'amarillo' || h.en_vigilancia)
  const c = n.conteo_estados

  return (
    <article className="reporte">
      <header className="reporte-portada">
        <p className="reporte-alcance">
          {n.area} · {nombreMes(n.periodo)}
        </p>
        <h1>Reporte ejecutivo de Recursos Humanos</h1>
        <p className="texto-secundario">
          Generado el {fechaHora(n.generado_en)} con {n.modelo ?? n.proveedor} ({n.proveedor === 'ollama' ? 'local' : 'nube'}),
          prompt {n.version_prompt}, {n.intentos === 1 ? '1 intento' : `${n.intentos} intentos`}.
        </p>
      </header>

      {aviso}

      <section>
        <h2>Resumen ejecutivo</h2>
        <p className="reporte-resumen">{n.resumen}</p>
        <ul className="resumen-estados">
          <li className="resumen-rojo">
            <strong>{c.rojo}</strong> en crítico
          </li>
          <li className="resumen-amarillo">
            <strong>{c.amarillo}</strong> en atención
          </li>
          <li className="resumen-verde">
            <strong>{c.verde}</strong> en rango
          </li>
          {c.por_vigilar > 0 && (
            <li className="resumen-neutro">
              <strong>{c.por_vigilar}</strong> por vigilar
            </li>
          )}
        </ul>
        {n.mes_estable && <p className="texto-secundario">Mes estable: sin alertas ni indicadores por vigilar.</p>}
      </section>

      {n.hallazgos.length > 0 && (
        <section>
          <h2>Hallazgos</h2>
          <ol className="lista-reporte">
            {n.hallazgos.map((h, i) => (
              <li key={i}>
                <div className="lista-reporte-encabezado">
                  <h3>{h.titulo}</h3>
                  <Confianza nivel={h.confianza} />
                </div>
                <p>{h.texto}</p>
                <Respaldo ids={h.hechos} hechos={hechos} fuentes={h.fuentes} />
              </li>
            ))}
          </ol>
        </section>
      )}

      {alertas.length > 0 && (
        <section>
          <h2>Alertas y riesgos</h2>
          <ul className="lista-alertas">
            {alertas.map((h) => (
              <li key={h.id}>
                {h.en_vigilancia && h.estado === 'verde' ? (
                  <span className="semaforo semaforo-neutro semaforo-pequeno">
                    <span className="semaforo-icono" aria-hidden="true">◐</span>
                    Por vigilar
                  </span>
                ) : (
                  <Semaforo estado={h.estado} pequeno />
                )}
                <span>
                  <strong>{h.nombre}</strong>: {h.valor_texto}
                  {h.motivo_vigilancia ? `; ${h.motivo_vigilancia}.` : `. El valor ${h.situacion}.`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {n.recomendaciones.length > 0 && (
        <section>
          <h2>Recomendaciones</h2>
          <ol className="lista-reporte">
            {n.recomendaciones.map((r, i) => (
              <li key={i}>
                <div className="lista-reporte-encabezado">
                  <p className="recomendacion">{r.accion}</p>
                  <Confianza nivel={r.confianza} />
                </div>
                <Respaldo ids={r.hechos} hechos={hechos} fuentes={r.fuentes} />
              </li>
            ))}
          </ol>
        </section>
      )}

      {n.indicadores_sin_evaluar.length > 0 && (
        <p className="texto-secundario">
          Sin evaluar por muestra insuficiente: {n.indicadores_sin_evaluar.join(', ')}.
        </p>
      )}

      <section>
        <h2>Anexo: indicadores y metodología</h2>
        <p className="texto-secundario">
          Cifras calculadas por el motor analítico, sin IA. La dirección del cambio y el nivel de confianza los
          calcula el sistema con reglas fijas, no el modelo.
        </p>
        <div className="tabla-desplazable">
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">Indicador</th>
                <th scope="col" className="num">Valor</th>
                <th scope="col">Vs mes anterior</th>
                <th scope="col">Vs año anterior</th>
                <th scope="col">Semáforo</th>
                <th scope="col">Confianza</th>
                <th scope="col">Fuente</th>
              </tr>
            </thead>
            <tbody>
              {n.hechos.map((h) => (
                <tr key={h.id}>
                  <td>
                    {h.nombre}
                    {h.personas_texto && <div className="nota">{h.personas_texto}</div>}
                  </td>
                  <td className="num">{h.valor_texto}</td>
                  <td>{h.var_mes_ant_texto ? `${h.var_mes_ant_texto} (${h.evolucion_mes_ant})` : '—'}</td>
                  <td>{h.var_anio_ant_texto ? `${h.var_anio_ant_texto} (${h.evolucion_anio_ant})` : '—'}</td>
                  <td>
                    <Semaforo estado={h.estado} pequeno />
                  </td>
                  <td title={h.motivo_confianza}>{h.confianza}</td>
                  <td>{h.fuente}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </article>
  )
}
