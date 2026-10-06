import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { SESION_VENCIDA } from '../api'
import App from '../App'
import { SEGUNDOS_ENTRE_CONSULTAS } from '../paginas/DetalleNarrativa'
import { ProveedorSesion } from '../sesion'
import { instalarApiFalsa } from './apiFalsa'

function montar(ruta = '/') {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <ProveedorSesion>
        <App />
      </ProveedorSesion>
    </MemoryRouter>,
  )
}

async function entrar(usuario, contrasena, ruta) {
  const persona = userEvent.setup({ advanceTimers: (ms) => vi.isFakeTimers() && vi.advanceTimersByTime(ms) })
  montar(ruta)
  await persona.type(screen.getByLabelText('Usuario'), usuario)
  await persona.type(screen.getByLabelText('Contraseña'), contrasena)
  await persona.click(screen.getByRole('button', { name: 'Entrar' }))
  return persona
}

describe('inicio de sesión', () => {
  it('muestra el mensaje de la API si la contraseña es incorrecta', async () => {
    instalarApiFalsa()
    await entrar('ana', 'equivocada')
    expect(await screen.findByRole('alert')).toHaveTextContent('Usuario o contraseña incorrectos')
    expect(screen.getByLabelText('Contraseña')).toHaveValue('')
  })

  it('avisa si la API no está encendida', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await entrar('ana', 'x')
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo conectar con la API')
  })

  it('al entrar guarda el token solo en sessionStorage y abre el tablero', async () => {
    const { contrasena } = instalarApiFalsa()
    await entrar('ana', contrasena)
    expect(await screen.findByRole('heading', { name: 'Indicadores de Corporativo' })).toBeInTheDocument()
    expect(sessionStorage.getItem('rrhh.token')).toBe('token-ana')
    expect(localStorage.length).toBe(0)
  })

  it('si la sesión vence, vuelve al inicio de sesión con un aviso', async () => {
    const api = instalarApiFalsa()
    await entrar('ana', api.contrasena)
    await screen.findByRole('heading', { name: 'Indicadores de Corporativo' })
    act(() => window.dispatchEvent(new CustomEvent(SESION_VENCIDA, { detail: 'Sesión no válida o vencida' })))
    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Sesión no válida o vencida')
    expect(sessionStorage.getItem('rrhh.token')).toBeNull()
  })

  it('cualquier 401 de la API cierra la sesión', async () => {
    const api = instalarApiFalsa()
    const persona = await entrar('ana', api.contrasena)
    await screen.findByRole('heading', { name: 'Indicadores de Corporativo' })
    api.estado.tokenValido = false
    await persona.selectOptions(screen.getByLabelText('Mes'), '2026-07')
    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument()
  })
})

describe('tablero', () => {
  it('muestra el semáforo con texto, el resumen y las variaciones', async () => {
    const { contrasena } = instalarApiFalsa()
    await entrar('ana', contrasena)
    const resumen = await screen.findByRole('list', { name: 'Resumen del semáforo' })
    expect(resumen).toHaveTextContent('1 en crítico')
    expect(resumen).toHaveTextContent('2 en rango')

    const rotacion = screen.getByRole('button', { name: /Tasa de rotación mensual/ })
    expect(rotacion).toHaveTextContent('3.9 %')
    expect(rotacion).toHaveTextContent('Crítico')
    // en rotacion subir es peor
    expect(rotacion).toHaveTextContent('+0.5 pts vs mes anterior (empeora)')
    expect(rotacion).toHaveTextContent('120 personas en promedio')
    // por defecto se grafica el indicador mas grave
    expect(rotacion).toHaveAttribute('aria-pressed', 'true')
  })

  it('al cambiar de área respeta la privacidad y la muestra mínima', async () => {
    const { contrasena } = instalarApiFalsa()
    const persona = await entrar('ana', contrasena)
    await screen.findByRole('heading', { name: 'Indicadores de Corporativo' })
    await persona.selectOptions(screen.getByLabelText('Área'), '2')
    expect(await screen.findByRole('heading', { name: 'Indicadores de Legal' })).toBeInTheDocument()

    const enps = await screen.findByRole('button', { name: /eNPS/ })
    expect(enps).toHaveTextContent('Oculto por privacidad')
    expect(enps).toHaveTextContent('menos de 5 personas')
    expect(enps).not.toHaveTextContent('vs mes anterior')
    const finalizacion = screen.getByRole('button', { name: /Tasa de finalización/ })
    expect(finalizacion).toHaveTextContent('Muestra insuficiente')
    expect(finalizacion).toHaveTextContent('muy pocas para el semáforo')
  })

  it('abre directo con los filtros de la URL (enlace compartido o recarga)', async () => {
    const { contrasena } = instalarApiFalsa()
    await entrar('ana', contrasena, '/tablero?area=1&periodo=2026-07&indicador=enps')
    expect(await screen.findByRole('heading', { name: 'Indicadores de Ventas' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /eNPS/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Mes')).toHaveValue('2026-07')
  })

  it('la gráfica tiene una vista de tabla accesible', async () => {
    const { contrasena } = instalarApiFalsa()
    const persona = await entrar('ana', contrasena)
    await persona.click(await screen.findByRole('button', { name: 'Ver como tabla' }))
    const tabla = screen.getByRole('table')
    expect(within(tabla).getAllByRole('row')).toHaveLength(4) // encabezado + 3 meses
    expect(tabla).toHaveTextContent('agosto 2026')
  })

  it('Dirección solo puede elegir el consolidado corporativo', async () => {
    const { contrasena } = instalarApiFalsa()
    await entrar('dir', contrasena)
    await screen.findByRole('heading', { name: 'Indicadores de Corporativo' })
    expect(screen.getByLabelText('Área')).toBeDisabled()
  })

  it('TI no ve datos de colaboradores: solo la configuración', async () => {
    const { contrasena, fetch } = instalarApiFalsa()
    await entrar('ti', contrasena, '/tablero')
    expect(await screen.findByRole('heading', { name: 'Umbrales del semáforo' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Tablero' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Narrativas' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Avisos/ })).not.toBeInTheDocument()
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/kpis'))).toBe(false)
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/avisos'))).toBe(false)
  })
})

describe('narrativas', () => {
  it('genera el reporte desde el tablero y lo muestra cuando termina', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const api = instalarApiFalsa({ consultasHastaLista: 1 })
    const persona = await entrar('ana', api.contrasena)
    await screen.findByRole('heading', { name: 'Indicadores de Corporativo' })

    await persona.click(screen.getByRole('button', { name: 'Generar reporte con IA' }))
    expect(api.estado.solicitudes).toEqual([{ periodo: '2026-08', area_id: 0 }])
    expect(await screen.findByRole('heading', { name: /Redactando el reporte de Corporativo, agosto 2026/ })).toBeInTheDocument()

    await act(() => vi.advanceTimersByTimeAsync(SEGUNDOS_ENTRE_CONSULTAS * 1000))
    expect(await screen.findByRole('heading', { name: 'Reporte ejecutivo de Recursos Humanos' })).toBeInTheDocument()
    expect(screen.getByText(/Borrador pendiente de revisión/)).toBeInTheDocument()
    // ana lo solicito: no puede aprobarlo ella misma
    expect(screen.getByText(/Tú lo solicitaste/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Aprobar' })).not.toBeInTheDocument()
    expect(screen.getByText('Rotación al alza')).toBeInTheDocument()
    expect(screen.getByText('Revisar las bajas del mes por área.')).toBeInTheDocument()
    expect(screen.getAllByText('Tasa de rotación mensual: 3.9 %').length).toBe(2)
    expect(screen.getByText(/solicitado por ana/)).toBeInTheDocument()
  })

  it('si el modelo falla muestra el motivo y nunca un texto de relleno', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const api = instalarApiFalsa({ consultasHastaLista: 0, fallaNarrativa: true })
    await entrar('ana', api.contrasena, '/narrativas/7')
    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('El modelo no pasó los guardarrailes')
    expect(alerta).toHaveTextContent('Cifra 4.2 no está en los hechos')
    expect(screen.queryByText('Reporte ejecutivo de Recursos Humanos')).not.toBeInTheDocument()
  })

  it('el historial lista los reportes con su estado y enlace', async () => {
    const { contrasena } = instalarApiFalsa()
    await entrar('ana', contrasena, '/narrativas')
    const tabla = await screen.findByRole('table')
    await waitFor(() => expect(within(tabla).getAllByRole('row')).toHaveLength(3))
    expect(tabla).toHaveTextContent('Pendiente de revisión')
    expect(tabla).toHaveTextContent('Error al generar')
    expect(tabla).toHaveTextContent('Ventas')
    expect(within(tabla).getByRole('link', { name: '#5' })).toHaveAttribute('href', '/narrativas/5')
  })
})

describe('revisión humana (RF-05)', () => {
  it('otra persona de RRHH aprueba el reporte y queda registrado', async () => {
    const { contrasena } = instalarApiFalsa()
    const persona = await entrar('eva', contrasena, '/narrativas/5')
    await screen.findByRole('heading', { name: 'Reporte ejecutivo de Recursos Humanos' })
    await persona.type(screen.getByLabelText(/Comentario/), 'Cifras revisadas contra el tablero')
    await persona.click(screen.getByRole('button', { name: 'Aprobar' }))
    expect(await screen.findByText(/Aprobado por eva/)).toBeInTheDocument()
    expect(screen.getByText(/Comentario: Cifras revisadas contra el tablero/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Aprobar' })).not.toBeInTheDocument()
    expect(screen.getByText(/aprobada por eva/)).toBeInTheDocument() // bitacora al pie
  })

  it('para rechazar pide el motivo y muestra el error de la API', async () => {
    const { contrasena } = instalarApiFalsa()
    const persona = await entrar('eva', contrasena, '/narrativas/5')
    await persona.click(await screen.findByRole('button', { name: 'Rechazar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Al rechazar, explica el motivo')

    await persona.type(screen.getByLabelText(/Comentario/), 'Falta el hallazgo de rotación de Ventas')
    await persona.click(screen.getByRole('button', { name: 'Rechazar' }))
    expect(await screen.findByText(/Rechazado por eva/)).toBeInTheDocument()
    expect(screen.getByText(/Motivo: Falta el hallazgo de rotación de Ventas/)).toBeInTheDocument()
  })

  it('Dirección ve el estado de la revisión pero no puede aprobar', async () => {
    const { contrasena } = instalarApiFalsa()
    await entrar('dir', contrasena, '/narrativas/5')
    expect(await screen.findByText(/Borrador pendiente de revisión/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Aprobar' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Tú lo solicitaste/)).not.toBeInTheDocument()
  })

  it('el historial filtra por revisión', async () => {
    const { contrasena, fetch } = instalarApiFalsa()
    const persona = await entrar('eva', contrasena, '/narrativas')
    await screen.findByRole('table')
    await persona.selectOptions(screen.getByLabelText('Revisión'), 'aprobada')
    await waitFor(() =>
      expect(fetch.mock.calls.some(([url]) => String(url).includes('revision=aprobada'))).toBe(true),
    )
  })
})

describe('exportación (RF-08)', () => {
  // Captura las descargas: jsdom no navega a enlaces blob:
  function espiarDescargas() {
    const descargas = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
      descargas.push(this.download)
    })
    return descargas
  }

  it('un reporte aprobado se descarga en PDF y como presentación', async () => {
    const { contrasena, estado } = instalarApiFalsa()
    const descargas = espiarDescargas()
    const persona = await entrar('eva', contrasena, '/narrativas/5')
    await persona.click(await screen.findByRole('button', { name: 'Aprobar' }))

    await persona.click(await screen.findByRole('button', { name: 'Descargar PDF' }))
    await waitFor(() => expect(descargas).toEqual(['reporte-rrhh-corporativo-2026-08.pdf']))
    await persona.click(screen.getByRole('button', { name: 'Descargar presentación' }))
    await waitFor(() => expect(descargas).toHaveLength(2))
    expect(descargas[1]).toBe('reporte-rrhh-corporativo-2026-08.pptx')
    expect(estado.exportaciones).toEqual([
      { id: 5, formato: 'pdf' },
      { id: 5, formato: 'pptx' },
    ])
  })

  it('un reporte pendiente no se puede descargar', async () => {
    const { contrasena, estado } = instalarApiFalsa()
    await entrar('dir', contrasena, '/narrativas/5')
    expect(await screen.findByText(/después se podrá descargar/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Descargar PDF' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Descargar presentación' })).not.toBeInTheDocument()
    expect(estado.exportaciones).toEqual([])
  })

  it('un reporte rechazado no ofrece descargas', async () => {
    const { contrasena } = instalarApiFalsa()
    const persona = await entrar('eva', contrasena, '/narrativas/5')
    await persona.type(await screen.findByLabelText(/Comentario/), 'Falta el hallazgo de rotación de Ventas')
    await persona.click(screen.getByRole('button', { name: 'Rechazar' }))
    expect(await screen.findByText(/Rechazado por eva/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Descargar PDF' })).not.toBeInTheDocument()
  })
})

describe('avisos (RF-09)', () => {
  it('el menú dice cuántos avisos faltan por leer', async () => {
    const { contrasena } = instalarApiFalsa()
    await entrar('ana', contrasena)
    const enlace = await screen.findByRole('link', { name: 'Avisos, 2 sin leer' })
    expect(enlace).toHaveAttribute('href', '/avisos')
  })

  it('al abrir un aviso se marca como leído y lleva a donde se atiende', async () => {
    const { contrasena, estado } = instalarApiFalsa()
    const persona = await entrar('ana', contrasena, '/avisos')
    const lista = await screen.findByRole('list', { name: 'Avisos' })
    expect(within(lista).getAllByRole('listitem')).toHaveLength(3)
    expect(lista).toHaveTextContent('Alerta')
    expect(lista).toHaveTextContent('Por revisar')
    expect(within(lista).getAllByText(/Nuevo/)).toHaveLength(2)

    await persona.click(screen.getByRole('link', { name: /1 indicador en rojo/ }))
    expect(await screen.findByRole('heading', { name: 'Indicadores de Corporativo' })).toBeInTheDocument()
    expect(estado.avisos.ana.find((a) => a.id === 11).leido_en).not.toBeNull()
    expect(await screen.findByRole('link', { name: 'Avisos, 1 sin leer' })).toBeInTheDocument()
  })

  it('marca todos como leídos', async () => {
    const { contrasena, estado } = instalarApiFalsa()
    const persona = await entrar('ana', contrasena, '/avisos')
    await persona.click(await screen.findByRole('button', { name: 'Marcar todos como leídos' }))
    await waitFor(() => expect(screen.queryByText(/Nuevo/)).not.toBeInTheDocument())
    expect(estado.avisos.ana.every((a) => a.leido_en)).toBe(true)
    expect(await screen.findByRole('link', { name: 'Avisos' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Marcar todos como leídos' })).not.toBeInTheDocument()
  })

  it('sin avisos lo dice', async () => {
    const { contrasena } = instalarApiFalsa()
    await entrar('dir', contrasena, '/avisos')
    expect(await screen.findByText('No tienes avisos.')).toBeInTheDocument()
  })
})

describe('configuración (RF-12)', () => {
  it('RRHH edita un umbral y el cambio queda en la bitácora', async () => {
    const { contrasena, estado } = instalarApiFalsa()
    const persona = await entrar('ana', contrasena, '/configuracion')
    await persona.click(await screen.findByRole('button', { name: 'Editar Tasa de rotación mensual' }))
    const atencion = screen.getByLabelText('Atención de Tasa de rotación mensual')
    const critico = screen.getByLabelText('Crítico de Tasa de rotación mensual')
    await persona.clear(atencion)
    await persona.type(atencion, '2.5')
    await persona.clear(critico)
    await persona.type(critico, '4')
    await persona.click(screen.getAllByRole('button', { name: 'Guardar' })[0])

    const cambios = await screen.findByRole('table', { name: 'Cambios de umbrales' })
    expect(cambios).toHaveTextContent('Tasa de rotación mensual')
    expect(cambios).toHaveTextContent('2.0 % / 3.5 %')
    expect(cambios).toHaveTextContent('2.5 % / 4.0 %')
    expect(cambios).toHaveTextContent('ana')
    expect(estado.umbrales.find((u) => u.indicador === 'rotacion_total').umbral_critico).toBe(4)
    expect(screen.queryByLabelText('Atención de Tasa de rotación mensual')).not.toBeInTheDocument()
  })

  it('muestra el motivo si la API rechaza el umbral', async () => {
    const { contrasena } = instalarApiFalsa()
    const persona = await entrar('ana', contrasena, '/configuracion')
    await persona.click(await screen.findByRole('button', { name: 'Editar Tasa de rotación mensual' }))
    const critico = screen.getByLabelText('Crítico de Tasa de rotación mensual')
    await persona.clear(critico)
    await persona.type(critico, '1')
    await persona.click(screen.getAllByRole('button', { name: 'Guardar' })[0])
    expect(await screen.findByRole('alert')).toHaveTextContent('un valor más alto es peor')
    expect(screen.getByLabelText('Crítico de Tasa de rotación mensual')).toBeInTheDocument() // sigue editando
  })

  it('RRHH activa la programación mensual', async () => {
    const { contrasena, estado } = instalarApiFalsa()
    const persona = await entrar('ana', contrasena, '/configuracion')
    const formulario = await screen.findByRole('checkbox', { name: 'Generar los reportes cada mes' })
    const guardar = formulario.closest('form').querySelector('button[type=submit]')
    expect(guardar).toBeDisabled() // sin cambios no hay nada que guardar
    expect(screen.getByRole('table', { name: 'Meses generados' })).toHaveTextContent('julio 2026')

    await persona.click(formulario)
    await persona.selectOptions(screen.getByLabelText('A partir del día'), '3')
    await persona.click(guardar)
    expect(await screen.findByText('Programación guardada.')).toBeInTheDocument()
    expect(estado.programacion).toMatchObject({ activa: true, dia_del_mes: 3, modificada_por: 'ana' })
    expect(screen.getByText(/Último cambio: ana/)).toBeInTheDocument()
  })

  it('Dirección ve la configuración pero no puede cambiarla', async () => {
    const { contrasena } = instalarApiFalsa()
    await entrar('dir', contrasena, '/configuracion')
    expect(await screen.findByText('Solo Recursos Humanos puede cambiar esta configuración.')).toBeInTheDocument()
    expect(await screen.findByText('Desactivada')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Generar los reportes cada mes')).not.toBeInTheDocument()
  })
})
