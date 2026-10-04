// Sesion de la persona usuaria: token, datos de /auth/yo y permisos por rol.
// Los permisos reales los aplica la API (403); aqui solo se adapta la interfaz.
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, guardarToken, leerToken, SESION_VENCIDA } from './api'

const ContextoSesion = createContext(null)

export const NOMBRES_ROL = {
  direccion: 'Dirección',
  rrhh: 'Recursos Humanos',
  gerente: 'Gerencia de área',
  admin_ti: 'Administración de TI',
}

// admin_ti administra catalogos y configuracion, sin datos de colaboradores
export const puedeVerDatos = (usuario) => usuario?.rol !== 'admin_ti'

export function ProveedorSesion({ children }) {
  const [usuario, setUsuario] = useState(null)
  const [cargando, setCargando] = useState(() => Boolean(leerToken()))
  const [aviso, setAviso] = useState(null) // motivo del ultimo cierre de sesion

  const cerrarSesion = useCallback((motivo = null) => {
    guardarToken(null)
    setUsuario(null)
    setAviso(motivo)
  }, [])

  // Al recargar la pagina: si hay token, recuperar la sesion
  useEffect(() => {
    if (!leerToken()) return
    api
      .yo()
      .then(setUsuario)
      .catch(() => guardarToken(null))
      .finally(() => setCargando(false))
  }, [])

  // Cualquier 401 de la API cierra la sesion
  useEffect(() => {
    const alVencer = (e) => cerrarSesion(e.detail || 'Tu sesión venció; vuelve a iniciar sesión.')
    window.addEventListener(SESION_VENCIDA, alVencer)
    return () => window.removeEventListener(SESION_VENCIDA, alVencer)
  }, [cerrarSesion])

  const iniciarSesion = useCallback(async (nombreUsuario, contrasena) => {
    const { access_token } = await api.login(nombreUsuario, contrasena)
    guardarToken(access_token)
    try {
      setUsuario(await api.yo())
      setAviso(null)
    } catch (error) {
      guardarToken(null)
      throw error
    }
  }, [])

  return (
    <ContextoSesion.Provider value={{ usuario, cargando, aviso, iniciarSesion, cerrarSesion }}>
      {children}
    </ContextoSesion.Provider>
  )
}

export function useSesion() {
  return useContext(ContextoSesion)
}
