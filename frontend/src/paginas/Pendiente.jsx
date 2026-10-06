import ConfigurarMfa from '../componentes/ConfigurarMfa'
import FormularioContrasena from '../componentes/FormularioContrasena'
import { useSesion } from '../sesion'

const TEXTOS = {
  cambiar_contrasena: {
    titulo: 'Cambia tu contraseña',
    texto: 'Entraste con una contraseña temporal. Elige la tuya para continuar: nadie más la conocerá.',
  },
  configurar_mfa: {
    titulo: 'Configura la verificación en dos pasos',
    texto:
      'Tu rol tiene acceso a información sensible, así que además de la contraseña necesitas un código de tu teléfono para entrar.',
  },
}

// Lo que hay que resolver antes de usar el sistema. La API exige lo mismo:
// hasta resolverlo, todo lo demas responde 403.
export default function Pendiente() {
  const { usuario, recargarUsuario, cerrarSesion } = useSesion()
  const { titulo, texto } = TEXTOS[usuario.pendiente]

  return (
    <main className="pagina-login">
      <div className="tarjeta-login tarjeta-ancha">
        <img src="/icono.svg" alt="" width="40" height="40" />
        <h1>{titulo}</h1>
        <p className="texto-secundario">
          Hola, {usuario.nombre}. {texto}
        </p>
        {usuario.pendiente === 'cambiar_contrasena' ? (
          <FormularioContrasena alCambiar={recargarUsuario} textoBoton="Guardar y continuar" />
        ) : (
          <ConfigurarMfa alTerminar={recargarUsuario} />
        )}
        <button type="button" className="boton-texto" onClick={() => cerrarSesion()}>
          Cerrar sesión
        </button>
      </div>
    </main>
  )
}
