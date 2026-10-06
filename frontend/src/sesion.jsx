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

// admin_ti administra catalogos, configuracion y cuentas, sin datos de colaboradores
export const puedeVerDatos = (usuario) => usuario?.rol !== 'admin_ti'

// Cuentas: TI las administra y RRHH las consulta (para auditar)
export const puedeVerCuentas = (usuario) => ['admin_ti', 'rrhh'].includes(usuario?.rol)

// Carga de datos de los sistemas fuente: solo RRHH (TI no ve datos de colaboradores)
export const puedeCargarDatos = (usuario) => usuario?.rol === 'rrhh'

export function ProveedorSesion({ children }) {
  const [usuario, setUsuario] = useState(null)
  const [cargando, setCargando] = useState(() => Boolean(leerToken()))
  const [aviso, setAviso] = useState(null) // motivo del ultimo cierre de sesion
  const [demo, setDemo] = useState({ activo: false }) // modo demostracion (GET /demo)
  const [marca, setMarca] = useState({ producto: 'Talentia Insights', empresa: '' })

  // Sin API, la pantalla de inicio ya muestra el error al intentar entrar
  useEffect(() => {
    api.demo().then(setDemo).catch(() => {})
    api.marca().then(setMarca).catch(() => {})
  }, [])

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

  // Guarda el token y carga quien es la persona
  const abrirSesion = useCallback(async (token) => {
    guardarToken(token)
    try {
      setUsuario(await api.yo())
      setAviso(null)
    } catch (error) {
      guardarToken(null)
      throw error
    }
  }, [])

  // Primer paso. Si la cuenta tiene verificacion en dos pasos, devuelve el
  // mfa_token para el segundo paso; si no, la sesion queda abierta.
  const iniciarSesion = useCallback(
    async (nombreUsuario, contrasena) => {
      const r = await api.login(nombreUsuario, contrasena)
      if (r.mfa_requerido) return r.mfa_token
      await abrirSesion(r.access_token)
      return null
    },
    [abrirSesion],
  )

  const verificarMfa = useCallback(
    async (mfaToken, codigo) => {
      const { access_token } = await api.verificarMfa(mfaToken, codigo)
      await abrirSesion(access_token)
    },
    [abrirSesion],
  )

  // Tras cambiar la contrasena o activar el MFA: datos y pendientes al dia
  const recargarUsuario = useCallback(async () => setUsuario(await api.yo()), [])

  return (
    <ContextoSesion.Provider
      value={{ usuario, cargando, aviso, demo, marca, iniciarSesion, verificarMfa, recargarUsuario, cerrarSesion }}
    >
      {children}
    </ContextoSesion.Provider>
  )
}

export function useSesion() {
  return useContext(ContextoSesion)
}
