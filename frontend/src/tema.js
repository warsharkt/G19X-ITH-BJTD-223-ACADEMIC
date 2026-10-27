// Diseno de la interfaz: claro (blanco) u oscuro. La primera vez sigue al
// sistema operativo; despues se recuerda lo que eligio la persona en este
// navegador. Es solo una preferencia visual, por eso puede ir en localStorage.
const CLAVE = 'talentia.tema'
export const TEMAS = ['claro', 'oscuro']

function guardado() {
  try {
    const valor = localStorage.getItem(CLAVE)
    return TEMAS.includes(valor) ? valor : null
  } catch {
    return null // navegacion privada o almacenamiento bloqueado
  }
}

function delSistema() {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro'
}

export function temaInicial() {
  return guardado() ?? delSistema()
}

export function aplicarTema(tema) {
  document.documentElement.dataset.theme = tema === 'oscuro' ? 'dark' : 'light'
}

export function guardarTema(tema) {
  aplicarTema(tema)
  try {
    localStorage.setItem(CLAVE, tema)
  } catch {
    // sin almacenamiento el cambio dura lo que dure la pestana
  }
}

export function temaActual() {
  return document.documentElement.dataset.theme === 'dark' ? 'oscuro' : 'claro'
}
