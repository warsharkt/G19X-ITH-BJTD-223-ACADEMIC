import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatoEje, formatoN, formatoValor, infoEstado, mesCorto, nombreMes } from '../formato'
import Semaforo from './Semaforo'

// Color del punto segun el semaforo de ese mes (tokens en estilos.css)
const COLOR_ESTADO = {
  verde: 'var(--estado-bueno)',
  amarillo: 'var(--estado-atencion)',
  rojo: 'var(--estado-critico)',
}

function Punto({ cx, cy, payload, seleccionado }) {
  if (cx == null || cy == null || payload.valor === null) return null
  const color = COLOR_ESTADO[payload.estado] ?? 'var(--texto-tenue)'
  const r = payload.periodo === seleccionado ? 6 : 4
  // anillo del color de la superficie: el punto se lee aunque cruce la linea
  return <circle cx={cx} cy={cy} r={r} fill={color} stroke="var(--superficie)" strokeWidth={2} />
}

function Globo({ active, payload, indicador, unidad }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="globo">
      <div className="globo-valor">{p.suprimido ? 'Oculto' : formatoValor(p.valor, unidad)}</div>
      <div className="globo-mes">{nombreMes(p.periodo)}</div>
      <Semaforo estado={p.estado} pequeno />
      {!p.suprimido && <div className="globo-base">{formatoN(p.n, indicador)}</div>}
    </div>
  )
}

// Paso "redondo" (1, 2, 2.5 o 5 por potencia de 10) para unas 4 divisiones
function pasoRedondo(rango) {
  const bruto = rango / 4
  const potencia = 10 ** Math.floor(Math.log10(bruto))
  return [1, 2, 2.5, 5, 10].map((m) => m * potencia).find((p) => p >= bruto)
}

// Marcas del eje Y en numeros redondos que incluyen los datos y los umbrales
export function marcasY(serie, umbral) {
  const valores = serie.map((p) => p.valor).filter((v) => v !== null)
  if (umbral) valores.push(umbral.umbral_atencion, umbral.umbral_critico)
  if (!valores.length) return [0, 1]
  const min = Math.min(...valores)
  const max = Math.max(...valores)
  const paso = pasoRedondo(max - min || Math.abs(max) || 1)
  const marcas = []
  for (let v = Math.floor(min / paso) * paso; v <= max + paso * 0.999; v += paso) {
    marcas.push(Number(v.toFixed(6)))
    if (marcas.at(-1) >= max) break
  }
  return marcas
}

// Tendencia de un indicador en todos los meses, con sus umbrales.
export default function GraficaSerie({ serie, kpi, umbral, periodoSeleccionado }) {
  const [verTabla, setVerTabla] = useState(false)
  const unidad = kpi.unidad
  const datos = serie.map((p) => ({ ...p, periodo: String(p.periodo).slice(0, 7) }))
  const seleccionado = periodoSeleccionado?.slice(0, 7)
  const marcas = marcasY(datos, umbral)
  const etiquetaUmbral = (texto, valor) => ({
    value: `${texto} ${formatoValor(valor, unidad)}`,
    position: 'insideTopRight',
    fill: 'var(--texto-secundario)',
    fontSize: 12,
  })

  return (
    <figure className="grafica">
      <figcaption className="grafica-titulo">
        <span>
          <strong>{kpi.nombre}</strong> · {kpi.area}, evolución mensual
        </span>
        <button type="button" className="boton-texto" onClick={() => setVerTabla((v) => !v)}>
          {verTabla ? 'Ver gráfica' : 'Ver como tabla'}
        </button>
      </figcaption>

      {verTabla ? (
        <div className="tabla-desplazable">
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">Mes</th>
                <th scope="col" className="num">Valor</th>
                <th scope="col">Semáforo</th>
                <th scope="col" className="num">Base</th>
              </tr>
            </thead>
            <tbody>
              {datos.map((p) => (
                <tr key={p.periodo} className={p.periodo === seleccionado ? 'fila-seleccionada' : undefined}>
                  <td>{nombreMes(p.periodo)}</td>
                  <td className="num">{p.suprimido ? 'Oculto' : formatoValor(p.valor, unidad)}</td>
                  <td>{infoEstado(p.estado).etiqueta}</td>
                  <td className="num">{p.suprimido ? '—' : p.n.toLocaleString('es-MX')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="grafica-lienzo">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={datos} margin={{ top: 16, right: 16, bottom: 4, left: 8 }}>
              <CartesianGrid vertical={false} stroke="var(--reticula)" />
              <XAxis
                dataKey="periodo"
                tickFormatter={mesCorto}
                stroke="var(--eje)"
                tick={{ fill: 'var(--texto-tenue)', fontSize: 12 }}
                tickLine={false}
                interval="preserveStartEnd"
                minTickGap={24}
              />
              <YAxis
                domain={[marcas[0], marcas.at(-1)]}
                ticks={marcas}
                tickFormatter={(v) => formatoEje(v, unidad)}
                stroke="var(--eje)"
                tick={{ fill: 'var(--texto-tenue)', fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                width={76}
              />
              {umbral && (
                <>
                  <ReferenceLine
                    y={umbral.umbral_atencion}
                    stroke="var(--estado-atencion)"
                    label={etiquetaUmbral('Atención', umbral.umbral_atencion)}
                  />
                  <ReferenceLine
                    y={umbral.umbral_critico}
                    stroke="var(--estado-critico)"
                    label={etiquetaUmbral('Crítico', umbral.umbral_critico)}
                  />
                </>
              )}
              {seleccionado && <ReferenceLine x={seleccionado} stroke="var(--eje)" />}
              <Tooltip
                content={<Globo indicador={kpi.indicador} unidad={unidad} />}
                cursor={{ stroke: 'var(--eje)', strokeWidth: 1 }}
              />
              <Line
                type="linear"
                dataKey="valor"
                stroke="var(--serie-1)"
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
                connectNulls={false}
                isAnimationActive={false}
                dot={<Punto seleccionado={seleccionado} />}
                activeDot={{ r: 6, stroke: 'var(--superficie)', strokeWidth: 2, fill: 'var(--serie-1)' }}
              />
            </LineChart>
          </ResponsiveContainer>
          <p className="grafica-leyenda">
            Cada punto lleva el color del semáforo de ese mes. Las líneas horizontales son los umbrales de
            atención y crítico; la vertical marca el mes elegido.
          </p>
        </div>
      )}
    </figure>
  )
}
