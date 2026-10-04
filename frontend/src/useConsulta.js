import { useEffect, useState } from 'react'

// Ejecuta una consulta a la API cada vez que cambian sus dependencias.
// Mientras recarga conserva los datos anteriores (la pantalla no "salta").
// Si `consulta` es null no hace nada (p. ej. faltan filtros por elegir).
export function useConsulta(consulta, dependencias) {
  const [estado, setEstado] = useState({ datos: null, error: null, cargando: Boolean(consulta) })

  useEffect(() => {
    if (!consulta) return
    let vigente = true // descarta respuestas que llegan tarde tras cambiar el filtro
    setEstado((previo) => ({ ...previo, cargando: true, error: null }))
    consulta()
      .then((datos) => vigente && setEstado({ datos, error: null, cargando: false }))
      .catch((error) => vigente && setEstado((previo) => ({ ...previo, error, cargando: false })))
    return () => {
      vigente = false
    }
    // Boolean(consulta): tambien se consulta cuando pasa de null a lista
    // aunque las dependencias no cambien (filtros que venian en la URL)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Boolean(consulta), ...dependencias])

  return estado
}
