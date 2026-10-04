import { describe, expect, it } from 'vitest'
import { evolucion, formatoN, formatoValor, formatoVariacion, mesCorto, nombreMes } from '../formato'

describe('formatoValor', () => {
  it('muestra cada unidad como la lee RRHH', () => {
    expect(formatoValor(12.345, '%')).toBe('12.3 %')
    expect(formatoValor(21500.4, 'MXN')).toBe('$21,500')
    expect(formatoValor(41, 'días')).toBe('41.0 días')
    expect(formatoValor(12, 'puntos')).toBe('+12')
    expect(formatoValor(-57, 'puntos')).toBe('-57')
  })

  it('usa un guion cuando no hay valor (suprimido o sin dato)', () => {
    expect(formatoValor(null, '%')).toBe('—')
  })
})

describe('formatoVariacion', () => {
  it('en porcentajes la diferencia va en puntos, como en la narrativa', () => {
    expect(formatoVariacion(-7.4, '%')).toBe('−7.4 pts')
    expect(formatoVariacion(10.7, 'días')).toBe('+10.7 días')
    expect(formatoVariacion(0, 'MXN')).toBe('±$0')
    expect(formatoVariacion(null, '%')).toBeNull()
  })

  it('redondea antes de poner el signo: nada de "−0.0 pts"', () => {
    expect(formatoVariacion(-0.04, '%')).toBe('±0.0 pts')
    expect(formatoVariacion(-0.4, 'puntos')).toBe('±0 pts')
  })
})

describe('evolucion', () => {
  it('depende del sentido del indicador', () => {
    // rotacion: subir es peor
    expect(evolucion(0.8, 'mayor_es_peor')).toBe('empeora')
    expect(evolucion(-0.8, 'mayor_es_peor')).toBe('mejora')
    // eNPS: bajar es peor
    expect(evolucion(-10, 'menor_es_peor')).toBe('empeora')
    expect(evolucion(10, 'menor_es_peor')).toBe('mejora')
    expect(evolucion(0, 'menor_es_peor')).toBe('neutra')
    expect(evolucion(null, 'menor_es_peor')).toBe('neutra')
    // un cambio que se muestra como 0.0 no "mejora" ni "empeora"
    expect(evolucion(-0.04, 'mayor_es_peor', '%')).toBe('neutra')
    expect(evolucion(-0.06, 'mayor_es_peor', '%')).toBe('mejora')
  })
})

describe('fechas', () => {
  it('nombra los meses en español', () => {
    expect(nombreMes('2026-04')).toBe('abril 2026')
    expect(nombreMes('2025-12-01')).toBe('diciembre 2025')
    expect(mesCorto('2026-01-01')).toBe('ene 26')
  })
})

it('formatoN explica qué cuenta la base de cada indicador', () => {
  expect(formatoN(1234, 'enps')).toBe('1,234 respuestas')
  expect(formatoN(1, 'tiempo_contratacion')).toBe('1 vacante cubierta')
  expect(formatoN(3, 'desconocido')).toBe('3 registros')
})
