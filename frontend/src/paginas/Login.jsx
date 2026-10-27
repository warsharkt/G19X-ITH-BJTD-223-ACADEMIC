import { useState } from 'react'
import BotonTema from '../componentes/BotonTema'
import Icono from '../componentes/Iconos'
import Marca from '../componentes/Marca'
import Mensaje from '../componentes/Mensaje'
import TelefonoSimulado from '../componentes/TelefonoSimulado'
import { useSesion } from '../sesion'

const SEGURIDAD = [
  ['escudo', 'Verificación en dos pasos', 'Además de la contraseña, un código de la app del celular.'],
  ['candado', 'Acceso por rol', 'Cada quien ve solo su área; TI no ve datos de colaboradores.'],
  ['bitacora', 'Todo queda registrado', 'Quién cargó, generó, firmó o descargó cada reporte.'],
  ['ia', 'IA revisada por personas', 'RRHH prepara cada reporte y su Responsable lo firma antes de distribuirlo.'],
]

// Modo demostracion: una tarjeta por rol que entra con un clic, sin
// contrasena ni codigo (solo cuentas de prueba y con datos ficticios).
function EntradaDemo({ demo, empresa, alUsarContrasena }) {
  const { entrarDemo } = useSesion()
  const [entrando, setEntrando] = useState(null)
  const [error, setError] = useState(null)

  async function entrar(usuario) {
    setError(null)
    setEntrando(usuario)
    try {
      await entrarDemo(usuario)
    } catch (err) {
      setError(err.message)
      setEntrando(null)
    }
  }

  return (
    <div className="tarjeta-login entrada-demo">
      <h1>Explora con un rol</h1>
      <p className="texto-secundario">
        Elige quién quieres ser{empresa && ` en ${empresa}`}. Puedes cambiar de rol en cualquier momento desde el
        menú.
      </p>
      {error && <Mensaje>{error}</Mensaje>}
      <ul className="roles-demo">
        {demo.cuentas.map((c) => (
          <li key={c.usuario}>
            <button
              type="button"
              className="rol-demo"
              disabled={entrando !== null}
              onClick={() => entrar(c.usuario)}
              aria-label={`Entrar como ${c.cargo}, ${c.nombre}`}
            >
              <span className="rol-demo-cargo">{c.cargo}</span>
              <span className="rol-demo-nombre">{c.nombre}</span>
              <span className="rol-demo-texto">{c.descripcion}</span>
              <span className="rol-demo-accion" aria-hidden="true">
                {entrando === c.usuario ? 'Entrando…' : 'Entrar →'}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <p className="nota">
        Demostración con datos ficticios. En producción cada persona entra con su cuenta y verificación en dos pasos.
      </p>
      <button type="button" className="boton-texto" onClick={alUsarContrasena}>
        Entrar con usuario y contraseña
      </button>
    </div>
  )
}

// Inicio de sesion en uno o dos pasos: contrasena y, si la cuenta tiene
// verificacion en dos pasos, el codigo de la app (o uno de respaldo).
export default function Login() {
  const { iniciarSesion, verificarMfa, aviso, demo, marca } = useSesion()
  const [conContrasena, setConContrasena] = useState(false) // en modo demo, el formulario es opcional
  const [usuario, setUsuario] = useState('')
  const [contrasena, setContrasena] = useState('')
  const [mfaToken, setMfaToken] = useState(null) // segundo paso pendiente
  const [codigo, setCodigo] = useState('')
  const [error, setError] = useState(null)
  const [enviando, setEnviando] = useState(false)

  async function enviar(e) {
    e.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      if (mfaToken) {
        await verificarMfa(mfaToken, codigo.trim())
      } else {
        const paso = await iniciarSesion(usuario.trim(), contrasena)
        setContrasena('')
        if (paso) setMfaToken(paso)
      }
    } catch (err) {
      setError(err.message)
      setContrasena('')
      setCodigo('')
      if (mfaToken && err.message.includes('venció')) setMfaToken(null) // volver a la contrasena
    } finally {
      setEnviando(false)
    }
  }

  function volver() {
    setMfaToken(null)
    setCodigo('')
    setError(null)
  }

  const conTarjetas = demo.activo && !conContrasena && !mfaToken

  return (
    <main className="pagina-login">
      <section className="login-marca" aria-label="Talentia Insights">
        <Marca tamano={40} />
        {mfaToken && demo.activo ? (
          <TelefonoSimulado mfaToken={mfaToken} usuario={usuario.trim().toLowerCase()} />
        ) : (
          <>
            <div className="login-lema">
              <h2>Decisiones sobre personas, con datos verificados.</h2>
              <p>
                Consolida tus sistemas de RRHH, calcula los indicadores y redacta reportes ejecutivos con IA que una
                persona revisa antes de distribuirse.
              </p>
            </div>
            <ul className="login-seguridad">
              {SEGURIDAD.map(([icono, titulo, texto]) => (
                <li key={titulo}>
                  <Icono nombre={icono} />
                  <span>
                    <strong>{titulo}</strong>
                    {texto}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
        {marca.empresa && (
          <p className="login-empresa">
            Espacio de trabajo de <strong>{marca.empresa}</strong>
          </p>
        )}
      </section>

      <section className="login-formulario">
        <div className="login-tema">
          <BotonTema />
        </div>
        {conTarjetas ? (
          <EntradaDemo demo={demo} empresa={marca.empresa} alUsarContrasena={() => setConContrasena(true)} />
        ) : (
          <form className="tarjeta-login" onSubmit={enviar}>
            <h1>{mfaToken ? 'Verificación en dos pasos' : 'Inicia sesión'}</h1>
            <p className="texto-secundario">
              {mfaToken
                ? 'Escribe el código de 6 dígitos de tu app de autenticación.'
                : 'Entra con tu cuenta personal: cada acción queda registrada a tu nombre.'}
            </p>

            {aviso && !error && !mfaToken && <Mensaje tipo="info">{aviso}</Mensaje>}
            {error && <Mensaje>{error}</Mensaje>}

            {mfaToken ? (
              <>
                <label>
                  Código de verificación
                  <input
                    name="codigo"
                    autoComplete="one-time-code"
                    inputMode="numeric"
                    value={codigo}
                    onChange={(e) => setCodigo(e.target.value)}
                    maxLength={20}
                    required
                    autoFocus
                  />
                </label>
                <button type="submit" className="boton-primario" disabled={enviando}>
                  {enviando ? 'Verificando…' : 'Verificar'}
                </button>
                <p className="nota">
                  ¿No tienes tu teléfono? Escribe uno de tus códigos de respaldo. Si tampoco los tienes, pide a TI que
                  reinicie tu verificación en dos pasos.
                </p>
                <button type="button" className="boton-texto" onClick={volver}>
                  Volver
                </button>
              </>
            ) : (
              <>
                <label>
                  Usuario
                  <input
                    name="usuario"
                    autoComplete="username"
                    value={usuario}
                    onChange={(e) => setUsuario(e.target.value)}
                    required
                    autoFocus
                  />
                </label>
                <label>
                  Contraseña
                  <input
                    name="contrasena"
                    type="password"
                    autoComplete="current-password"
                    value={contrasena}
                    onChange={(e) => setContrasena(e.target.value)}
                    required
                  />
                </label>
                <button type="submit" className="boton-primario" disabled={enviando}>
                  {enviando ? 'Entrando…' : 'Entrar'}
                </button>
                <p className="nota">Tras 5 intentos fallidos seguidos la cuenta se bloquea unos minutos.</p>
                {demo.activo && (
                  <>
                    <p className="nota">
                      Para ver la verificación en dos pasos con el teléfono simulado, usa una cuenta de prueba (por
                      ejemplo <code className="clave-demo">{demo.cuentas[1]?.usuario ?? 'demo_rrhh'}</code>) con la
                      contraseña <code className="clave-demo">{demo.contrasena}</code>.
                    </p>
                    <button type="button" className="boton-texto" onClick={() => setConContrasena(false)}>
                      ← Volver a elegir un rol
                    </button>
                  </>
                )}
              </>
            )}
          </form>
        )}
      </section>
    </main>
  )
}
