import { useState } from 'react'
import ConfigurarMfa from '../componentes/ConfigurarMfa'
import FormularioContrasena from '../componentes/FormularioContrasena'
import Mensaje from '../componentes/Mensaje'
import { NOMBRES_ROL, useSesion } from '../sesion'

// Mi cuenta: datos, cambio de contrasena y verificacion en dos pasos.
export default function Cuenta() {
  const { usuario, recargarUsuario } = useSesion()
  const [contrasenaCambiada, setContrasenaCambiada] = useState(false)
  const [configurando, setConfigurando] = useState(false)

  return (
    <div className="pagina-angosta">
      <div className="titulo-pagina">
        <div>
          <h1>Mi cuenta</h1>
          <p className="texto-secundario">
            {usuario.nombre} · {usuario.usuario} · {NOMBRES_ROL[usuario.rol] ?? usuario.rol}
          </p>
        </div>
      </div>

      <section className="seccion panel">
        <h2>Contraseña</h2>
        {contrasenaCambiada && (
          <Mensaje tipo="exito">Contraseña cambiada. Se cerraron tus sesiones en otros equipos.</Mensaje>
        )}
        <FormularioContrasena
          alCambiar={async () => {
            setContrasenaCambiada(true)
            await recargarUsuario()
          }}
        />
      </section>

      <section className="seccion panel">
        <h2>Verificación en dos pasos</h2>
        {usuario.mfa_activo ? (
          <>
            <p>
              <strong>Activa.</strong> Te quedan {usuario.codigos_respaldo_restantes} códigos de respaldo.
            </p>
            <p className="nota">
              Si pierdes tu teléfono, entra con un código de respaldo o pide a TI que reinicie tu verificación en dos
              pasos.
            </p>
          </>
        ) : configurando ? (
          <ConfigurarMfa
            alTerminar={async () => {
              setConfigurando(false)
              await recargarUsuario()
            }}
          />
        ) : (
          <>
            <p>No está activa. Es opcional para tu rol, pero protege tu cuenta aunque alguien conozca tu contraseña.</p>
            <button type="button" className="boton-primario" onClick={() => setConfigurando(true)}>
              Activar verificación en dos pasos
            </button>
          </>
        )}
      </section>
    </div>
  )
}
