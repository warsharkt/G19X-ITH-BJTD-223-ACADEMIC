import { api } from '../api'
import Mensaje from '../componentes/Mensaje'
import { formatoValor, INDICADORES, ordenIndicador } from '../formato'
import { puedeVerDatos, useSesion } from '../sesion'
import { useConsulta } from '../useConsulta'

const SENTIDO = { mayor_es_peor: 'Peor si sube', menor_es_peor: 'Peor si baja' }

// Catalogo de umbrales del semaforo (seccion 10.2 del PRD). Solo lectura:
// el panel para editarlos es el RF-12.
export default function Umbrales() {
  const { usuario } = useSesion()
  const umbrales = useConsulta(() => api.umbrales(), [])

  return (
    <div>
      <div className="titulo-pagina">
        <div>
          <h1>Umbrales del semáforo</h1>
          <p className="texto-secundario">
            Valores que definen cuándo un indicador pasa a atención o a crítico. Los define Recursos Humanos.
          </p>
        </div>
      </div>
      {!puedeVerDatos(usuario) && (
        <Mensaje tipo="info">
          Tu rol administra catálogos y configuración; no tiene acceso a datos de colaboradores.
        </Mensaje>
      )}
      {umbrales.error && <Mensaje>{umbrales.error.message}</Mensaje>}
      {umbrales.datos && (
        <div className="panel tabla-desplazable">
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">Proceso</th>
                <th scope="col">Indicador</th>
                <th scope="col">Sentido</th>
                <th scope="col" className="num">Atención</th>
                <th scope="col" className="num">Crítico</th>
              </tr>
            </thead>
            <tbody>
              {[...umbrales.datos]
                .sort((a, b) => ordenIndicador(a.indicador) - ordenIndicador(b.indicador))
                .map((u) => (
                  <tr key={u.indicador}>
                    <td>{INDICADORES[u.indicador]?.proceso ?? '—'}</td>
                    <td>{u.nombre}</td>
                    <td>{SENTIDO[u.sentido] ?? u.sentido}</td>
                    <td className="num">{formatoValor(u.umbral_atencion, u.unidad)}</td>
                    <td className="num">{formatoValor(u.umbral_critico, u.unidad)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
