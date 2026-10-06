import { useEffect, useState } from 'react'
import { api } from '../api'
import Icono from './Iconos'

const PERIODO = 30 // segundos que dura cada codigo TOTP
const RADIO = 15
const CIRCUNFERENCIA = 2 * Math.PI * RADIO

// "123456" -> "123 456", como lo muestran las apps de autenticacion
const separar = (codigo) => `${codigo.slice(0, 3)} ${codigo.slice(3)}`

function hora() {
  return new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', hour12: false })
}

// Telefono dibujado con la app de autenticacion abierta. Solo existe en la
// demostracion: la API da el codigo vigente unicamente para cuentas de
// demostracion y nunca con datos reales. Asi quien prueba recorre la
// verificacion en dos pasos completa sin necesitar un celular.
// Con mfaToken muestra el codigo para entrar; sin el, el del QR que se esta
// configurando.
export default function TelefonoSimulado({ mfaToken, usuario, enTarjeta = false }) {
  const [ronda, setRonda] = useState(0) // cada cambio pide el codigo de nuevo
  const [codigo, setCodigo] = useState(null)
  const [restan, setRestan] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let vigente = true
    const pedido = mfaToken ? api.codigoDemo(mfaToken) : api.codigoDemoConfiguracion()
    pedido
      .then((d) => {
        if (!vigente) return
        setCodigo(d.codigo)
        setRestan(d.segundos)
        setError(null)
      })
      .catch((err) => vigente && setError(err.message))
    return () => {
      vigente = false
    }
  }, [mfaToken, ronda])

  // Cuenta regresiva; al llegar a 0 el codigo cambio y se pide el nuevo
  useEffect(() => {
    if (restan === null) return
    if (restan <= 0) {
      setRonda((r) => r + 1)
      return
    }
    const reloj = setTimeout(() => setRestan(restan - 1), 1000)
    return () => clearTimeout(reloj)
  }, [restan])

  // el codigo "siguiente" dura un poco mas de 30 s: el anillo se queda lleno
  const avance = restan ? Math.min(1, restan / PERIODO) * CIRCUNFERENCIA : 0

  return (
    <figure className={`telefono-escena${enTarjeta ? ' en-tarjeta' : ''}`} aria-label="Teléfono simulado">
      <div className="telefono" role="note" aria-label="App de autenticación simulada">
        <div className="telefono-pantalla">
          <div className="telefono-isla" />
          <div className="telefono-barra" aria-hidden="true">
            <span>{hora()}</span>
            <span>5G ▮▮▮</span>
          </div>
          <div className="app-autenticador">
            <header>
              <Icono nombre="escudo" />
              Autenticador
            </header>
            <div className="cuenta-otp">
              <span className="cuenta-otp-emisor">Talentia Insights</span>
              <span className="cuenta-otp-usuario">{usuario}</span>
              {error ? (
                <span className="nota">{error}</span>
              ) : (
                <div className="cuenta-otp-fila">
                  <span className="cuenta-otp-codigo" aria-label="Código vigente">
                    {codigo ? separar(codigo) : '··· ···'}
                  </span>
                  <svg className="anillo-otp" width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">
                    <circle className="fondo" cx="20" cy="20" r={RADIO} />
                    <circle
                      className="avance"
                      cx="20"
                      cy="20"
                      r={RADIO}
                      strokeDasharray={CIRCUNFERENCIA}
                      strokeDashoffset={CIRCUNFERENCIA - avance}
                    />
                    <text x="20" y="23.5" textAnchor="middle">
                      {restan ?? ''}
                    </text>
                  </svg>
                </div>
              )}
              {restan > 0 && <span className="oculto-visual">Cambia en {restan} s</span>}
            </div>
            <div className="cuenta-otp cuenta-otp-otra" aria-hidden="true">
              <span className="cuenta-otp-emisor">Correo corporativo</span>
              <span className="cuenta-otp-codigo">••• •••</span>
            </div>
          </div>
        </div>
      </div>
      <figcaption className="telefono-nota">
        <Icono nombre="telefono" tamano={16} />
        Simulación para la demostración: en producción este código solo aparece en el celular de cada persona.
      </figcaption>
    </figure>
  )
}
