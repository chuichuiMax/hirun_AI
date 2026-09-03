import { describe, expect, it } from 'vitest'
import { normalizeHyCanvasSessionUrl } from '../hycanvasSession'

describe('normalizeHyCanvasSessionUrl', () => {
  it('uses the ContentSwarm loopback hostname for the HyCanvas iframe', () => {
    const result = normalizeHyCanvasSessionUrl(
      'http://127.0.0.1:8005/api/v1/auth/integration?ticket=test&next=%2Fdashboard%2F',
      'http://localhost:5173/hycanvas'
    )

    expect(result).toBe(
      'http://localhost:8005/api/v1/auth/integration?ticket=test&next=%2Fdashboard%2F'
    )
  })

  it('rewrites loopback HyCanvas URLs to the LAN host used by ContentFlow', () => {
    const result = normalizeHyCanvasSessionUrl(
      'http://127.0.0.1:8005/api/v1/auth/integration?ticket=test&next=%2Fdashboard%2F',
      'http://10.80.18.218:5173/hycanvas'
    )

    expect(result).toBe(
      'http://10.80.18.218:8005/api/v1/auth/integration?ticket=test&next=%2Fdashboard%2F'
    )
  })

  it('does not rewrite a configured remote HyCanvas host', () => {
    expect(
      normalizeHyCanvasSessionUrl(
        'https://canvas.example/api/v1/auth/integration?ticket=test',
        'http://localhost:5173/hycanvas'
      )
    ).toBe('https://canvas.example/api/v1/auth/integration?ticket=test')
  })
})
