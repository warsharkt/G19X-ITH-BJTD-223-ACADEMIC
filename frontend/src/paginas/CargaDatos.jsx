import { useRef, useState } from 'react'
import { api } from '../api'
import { guardarArchivo } from '../archivos'
import Icono from '../componentes/Iconos'
import Mensaje from '../componentes/Mensaje'
import { fechaHora, nombreMes } from '../formato'
import { useConsulta } from '../useConsulta'

const ESTADOS = {
  validada: { texto: 'Lista para aplicar', clase: 'amarillo', icono: '●' },
  con_errores: { texto: 'Con errores', clase: 'rojo', icono: '✕' },
  aplicada: { texto: 'Aplicada', clase: 'verde', icono: '✓' },
  descartada: { texto: 'Descartada', clase: 'neutro', icono: '—' },
}

const SELLOS = [
  ['todo_o_nada', 'Todo o nada: un archivo con errores no se carga'],
  ['ojo_cerrado', 'Solo códigos: los datos personales se descartan'],
  ['huella', 'Huella SHA-256 de cada archivo'],
  ['escudo', 'Conciliación archivo contra base'],
  ['bitacora', 'Bitácora de quién cargó qué'],
]

const PASOS = [
  ['Exporta de cada sistema', 'Saca de HRIS, ATS, LMS… el reporte que dice cada tarjeta, en Excel o CSV.'],
  ['Importa aquí', 'Con «Importar datos» en la tarjeta de esa fuente, empezando por la plantilla de personal.'],
  ['Revisa y aplica', 'El sistema valida el archivo completo; nada se guarda hasta que lo apliques.'],
]

const numero = (n) => (typeof n === 'number' ? n.toLocaleString('es-MX') : n)

function Estado({ estado }) {
  const e = ESTADOS[estado] ?? { texto: estado, clase: 'neutro', icono: '•' }
  return (
    <span className={`semaforo semaforo-${e.clase} semaforo-pequeno`}>
      <span className="semaforo-icono" aria-hidden="true">
        {e.icono}
      </span>
      {e.texto}
    </span>
  )
}

// Lo que encontro la validacion y, si se aplico, la conciliacion
function RevisionCarga({ carga, fuente, alCambiar }) {
  const [enviando, setEnviando] = useState(null)
  const [error, setError] = useState(null)
  const previo = carga.resultado?.previo ?? {}
  const esClima = carga.fuente === 'clima'

  async function decidir(accion) {
    setError(null)
    setEnviando(accion)
    try {
      alCambiar(await (accion === 'aplicar' ? api.aplicarCarga(carga.id) : api.descartarCarga(carga.id)))
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(null)
    }
  }

  return (
    <section className="revision-carga" aria-label="Revisión del archivo">
      <header>
        <div>
          <h2>
            {fuente?.nombre ?? carga.fuente}: {carga.archivo}
          </h2>
          <span className="huella" title={carga.sha256}>
            SHA-256 {carga.sha256.slice(0, 16)}… · subido por {carga.subida_por} el {fechaHora(carga.subida_en)}
          </span>
        </div>
        <Estado estado={carga.estado} />
      </header>

      <div className="cifras-carga">
        <div className="cifra">
          <strong>{numero(carga.filas)}</strong>
          <span>filas en el archivo</span>
        </div>
        {carga.estado !== 'con_errores' && (
          <>
            <div className="cifra">
              <strong>{numero(carga.resultado?.nuevas ?? previo.nuevas)}</strong>
              <span>{esClima ? 'respuestas (reemplazan la encuesta del mes)' : carga.estado === 'aplicada' ? 'nuevas: se agregaron' : 'nuevas: se agregarán'}</span>
            </div>
            {!esClima && (
              <div className="cifra">
                <strong>{numero(carga.resultado?.actualizadas ?? previo.existentes)}</strong>
                <span>{carga.estado === 'aplicada' ? 'ya existían: se actualizaron' : 'ya existían: se actualizarán'}</span>
              </div>
            )}
          </>
        )}
        {carga.estado === 'con_errores' && (
          <div className="cifra">
            <strong>{numero(carga.resultado?.errores_totales ?? carga.errores.length)}</strong>
            <span>errores</span>
          </div>
        )}
        {carga.periodos.length > 0 && (
          <div className="cifra">
            <strong>{carga.periodos.map(nombreMes).join(', ')}</strong>
            <span>meses que abarca</span>
          </div>
        )}
      </div>

      {carga.descartadas.length > 0 && (
        <div>
          <h3>Columnas que no se guardaron</h3>
          <ul className="descartadas">
            {carga.descartadas.map((d) => (
              <li key={d.columna}>
                <span className={d.motivo.startsWith('dato personal') ? 'personal' : 'nota'}>
                  <Icono nombre={d.motivo.startsWith('dato personal') ? 'ojo_cerrado' : 'archivo'} tamano={16} />
                </span>
                <code>{d.columna}</code> <span className="nota">{d.motivo}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {carga.errores.length > 0 && (
        <div>
          <Mensaje titulo="El archivo no se puede cargar">
            Corrige estas filas en el archivo y vuelve a subirlo: no se guardó nada.
          </Mensaje>
          <div className="tabla-desplazable">
            <table className="tabla" aria-label="Errores del archivo">
              <thead>
                <tr>
                  <th scope="col" className="num">Fila</th>
                  <th scope="col">Columna</th>
                  <th scope="col">Problema</th>
                </tr>
              </thead>
              <tbody>
                {carga.errores.map((e, i) => (
                  <tr key={i}>
                    <td className="num">{e.fila ?? '—'}</td>
                    <td>{e.columna ? <code>{e.columna}</code> : '—'}</td>
                    <td>{e.mensaje}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(carga.resultado?.errores_totales ?? 0) > carga.errores.length && (
            <p className="nota">
              Se muestran los primeros {carga.errores.length} de {carga.resultado.errores_totales} errores.
            </p>
          )}
        </div>
      )}

      {carga.estado === 'validada' && carga.resultado?.muestra?.filas?.length > 0 && (
        <div>
          <h3>
            Vista previa: las primeras {carga.resultado.muestra.filas.length} de {numero(carga.filas)} filas
          </h3>
          <p className="nota">Solo es una muestra para revisar el formato: al aplicar se importan todas las filas.</p>
          <div className="tabla-desplazable">
            <table className="tabla" aria-label="Vista previa">
              <thead>
                <tr>
                  {carga.resultado.muestra.columnas.map((c) => (
                    <th scope="col" key={c}>
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {carga.resultado.muestra.filas.map((fila, i) => (
                  <tr key={i}>
                    {fila.map((v, j) => (
                      <td key={j}>{v ?? '—'}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {carga.estado === 'aplicada' && (
        <div>
          <Mensaje tipo="exito" titulo="Datos cargados">
            El tablero ya los muestra y se revisaron las alertas del mes. Aplicada por {carga.aplicada_por} el{' '}
            {fechaHora(carga.aplicada_en)}
          </Mensaje>
          <h3>Conciliación</h3>
          <div className="tabla-desplazable">
            <table className="tabla" aria-label="Conciliación">
              <thead>
                <tr>
                  <th scope="col">Concepto</th>
                  <th scope="col" className="num">Archivo</th>
                  <th scope="col" className="num">Base de datos</th>
                  <th scope="col">Resultado</th>
                </tr>
              </thead>
              <tbody>
                {carga.resultado.conciliacion.map((c) => (
                  <tr key={c.concepto}>
                    <td>{c.concepto}</td>
                    <td className="num">{numero(c.archivo)}</td>
                    <td className="num">{numero(c.base)}</td>
                    <td className={c.cuadra ? 'cuadra' : 'no-cuadra'}>{c.cuadra ? '✓ Cuadra' : '✕ No cuadra'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {error && <Mensaje>{error}</Mensaje>}
      {(carga.estado === 'validada' || carga.estado === 'con_errores') && (
        <div className="botones">
          {carga.estado === 'validada' && (
            <button type="button" className="boton-primario" disabled={enviando} onClick={() => decidir('aplicar')}>
              {enviando === 'aplicar' ? 'Aplicando…' : 'Aplicar a la base de datos'}
            </button>
          )}
          <button type="button" className="boton-secundario" disabled={enviando} onClick={() => decidir('descartar')}>
            Descartar
          </button>
        </div>
      )}
    </section>
  )
}

// Carga de datos (RF-01): lo que exporta cada sistema de RRHH entra al motor
// analitico solo si pasa todas las validaciones. Solo RRHH.
export default function CargaDatos() {
  const catalogo = useConsulta(() => api.fuentesDeDatos(), [])
  const [version, setVersion] = useState(0)
  const historial = useConsulta(() => api.cargas(), [version])
  const [revision, setRevision] = useState(null)
  const [subiendo, setSubiendo] = useState(null)
  const [error, setError] = useState(null)
  const panel = useRef(null)

  const fuentes = catalogo.datos?.fuentes ?? []
  const ejemplos = catalogo.datos?.ejemplos

  async function subir(fuente, archivo) {
    if (!archivo) return
    setError(null)
    setSubiendo(fuente.clave)
    try {
      setRevision(await api.subirArchivo(fuente.clave, archivo))
      setVersion((v) => v + 1)
      setTimeout(() => panel.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' }), 0)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubiendo(null)
    }
  }

  async function descargar(pedido) {
    setError(null)
    try {
      const { blob, nombre } = await pedido()
      guardarArchivo(blob, nombre)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <div className="titulo-pagina">
        <div>
          <h1>Carga de datos</h1>
          <p className="texto-secundario">
            Aquí no se capturan datos: se suben los reportes que exportas de cada sistema de RRHH.
          </p>
        </div>
      </div>

      <ol className="pasos-carga" aria-label="Cómo se cargan los datos">
        {PASOS.map(([titulo, texto], i) => (
          <li key={titulo}>
            <span className="paso-fuente" aria-hidden="true">
              {i + 1}
            </span>
            <div>
              <strong>{titulo}</strong>
              <p>{texto}</p>
            </div>
          </li>
        ))}
      </ol>

      <ul className="sellos" aria-label="Controles de la carga">
        {SELLOS.map(([icono, texto]) => (
          <li key={texto}>
            <Icono nombre={icono} tamano={16} />
            {texto}
          </li>
        ))}
      </ul>

      {catalogo.error && <Mensaje>{catalogo.error.message}</Mensaje>}
      {error && <Mensaje>{error}</Mensaje>}
      {ejemplos && (
        <Mensaje tipo="info" titulo={ejemplos.mes ? `Mes pendiente: ${ejemplos.nombre_mes}` : 'Sin meses pendientes'}>
          {ejemplos.mes
            ? `Exporta de cada sistema los archivos de ${ejemplos.nombre_mes} e impórtalos en orden, empezando por la plantilla de personal: al aplicar las seis fuentes, el mes aparece completo en el tablero.`
            : 'Ya están cargados todos los meses cerrados. El siguiente se importa cuando cierre.'}
          {ejemplos.mes && ejemplos.descargables && (
            <span className="nota-simulacion">
              Simulación: los botones «Exportar {ejemplos.nombre_mes}» hacen lo que haría cada sistema de Nordika. En
              producción el archivo se saca del propio HRIS, ATS, LMS…
            </span>
          )}
        </Mensaje>
      )}

      <div ref={panel}>
        {revision && (
          <RevisionCarga
            key={`${revision.id}-${revision.estado}`}
            carga={revision}
            fuente={fuentes.find((f) => f.clave === revision.fuente)}
            alCambiar={(c) => {
              setRevision(c)
              setVersion((v) => v + 1)
            }}
          />
        )}
      </div>

      <div className="rejilla-fuentes">
        {fuentes.map((f, i) => {
          // la bitacora viene de la mas reciente a la mas antigua
          const ultima = historial.datos?.find((c) => c.fuente === f.clave)
          const opcionales = f.columnas.some((c) => !c.requerida)
          return (
            <article className="tarjeta-fuente" key={f.clave} aria-label={f.nombre}>
              <header className="cabeza-fuente">
                <span className="paso-fuente" aria-hidden="true">
                  {i + 1}
                </span>
                <div className="titulo-fuente">
                  <h3>{f.nombre}</h3>
                  <span className="sistema-fuente">{f.sistema}</span>
                </div>
                {ultima ? (
                  <span title={`Último archivo: ${ultima.archivo}, ${fechaHora(ultima.subida_en)}`}>
                    <Estado estado={ultima.estado} />
                  </span>
                ) : (
                  <span className="semaforo semaforo-neutro semaforo-pequeno">Sin importar</span>
                )}
              </header>

              <div className="cuerpo-fuente">
                <p>{f.descripcion}</p>
                <div className="exportar-fuente">
                  <Icono nombre="archivo" tamano={18} />
                  <div>
                    <strong>Qué exportar de {f.sistema}</strong>
                    <p>{f.exportar}</p>
                    {ejemplos?.mes && ejemplos.descargables && (
                      <button
                        type="button"
                        className="boton-secundario boton-exportar"
                        aria-label={`Exportar ${ejemplos.nombre_mes} de ${f.sistema}`}
                        title={`Simula la exportación de ${f.sistema}: el archivo de ${ejemplos.nombre_mes}, solo de ese mes`}
                        onClick={() => descargar(() => api.ejemploDeCarga(f.clave))}
                      >
                        <Icono nombre="descargar" tamano={16} /> Exportar {ejemplos.nombre_mes}
                      </button>
                    )}
                  </div>
                </div>
                <details className="columnas-detalle">
                  <summary>Columnas del archivo ({f.columnas.length})</summary>
                  <div className="columnas-fuente" aria-label="Columnas">
                    {f.columnas.map((c) => (
                      <code key={c.nombre} className={c.requerida ? undefined : 'opcional'} title={c.ayuda || undefined}>
                        {c.nombre}
                        {!c.requerida && '?'}
                      </code>
                    ))}
                  </div>
                  {opcionales && <p className="nota">Las que llevan ? pueden ir vacías.</p>}
                </details>
              </div>

              <footer className="pie-fuente">
                <label className="boton-primario subir-archivo">
                  <Icono nombre="carga" tamano={18} />
                  {subiendo === f.clave ? 'Validando…' : 'Importar datos'}
                  <input
                    type="file"
                    accept=".csv,.xlsx"
                    aria-label={`Importar datos de ${f.nombre}`}
                    disabled={Boolean(subiendo)}
                    onChange={(e) => {
                      subir(f, e.target.files[0])
                      e.target.value = ''
                    }}
                  />
                </label>
                <div className="descargas-fuente">
                  <button
                    type="button"
                    className="boton-texto"
                    aria-label={`Descargar formato vacío de ${f.nombre}`}
                    title="Excel vacío con las columnas, por si tu sistema no exporta en este formato"
                    onClick={() => descargar(() => api.plantilla(f.clave))}
                  >
                    <Icono nombre="descargar" tamano={16} /> Formato vacío
                  </button>
                </div>
              </footer>
            </article>
          )
        })}
      </div>

      <section className="seccion">
        <h2>Bitácora de cargas</h2>
        {historial.error && <Mensaje>{historial.error.message}</Mensaje>}
        {historial.datos?.length === 0 && <p className="nota">Todavía no se ha subido ningún archivo.</p>}
        {historial.datos?.length > 0 && (
          <div className="panel tabla-desplazable">
            <table className="tabla" aria-label="Bitácora de cargas">
              <thead>
                <tr>
                  <th scope="col">Fecha</th>
                  <th scope="col">Fuente</th>
                  <th scope="col">Archivo</th>
                  <th scope="col" className="num">Filas</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Subió</th>
                  <th scope="col">Aplicó o descartó</th>
                  <th scope="col">Huella</th>
                </tr>
              </thead>
              <tbody>
                {historial.datos.map((c) => (
                  <tr key={c.id}>
                    <td>{fechaHora(c.subida_en)}</td>
                    <td>{fuentes.find((f) => f.clave === c.fuente)?.nombre ?? c.fuente}</td>
                    <td>
                      <button type="button" className="boton-texto" onClick={() => setRevision(c)}>
                        {c.archivo}
                      </button>
                    </td>
                    <td className="num">{numero(c.filas)}</td>
                    <td>
                      <Estado estado={c.estado} />
                    </td>
                    <td>{c.subida_por}</td>
                    <td>{c.aplicada_por ?? '—'}</td>
                    <td className="huella" title={c.sha256}>
                      {c.sha256.slice(0, 10)}…
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
