import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  sessionStorage.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

// Recharts mide su contenedor; jsdom no tiene ResizeObserver
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// jsdom no implementa las descargas de archivos (exportar reportes)
URL.createObjectURL ??= () => 'blob:prueba'
URL.revokeObjectURL ??= () => {}
