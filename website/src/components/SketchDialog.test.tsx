import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import SketchDialog from './SketchDialog'

/** Captured from the mock's props so the persistence test can assert what a
 *  fresh mount was seeded with. */
let lastInitialData: { elements?: unknown[]; files?: Record<string, unknown>; appState?: Record<string, unknown> } | null = null

/** Fake imperative API standing in for Excalidraw's. `elements` is mutable so
 *  individual tests can model an empty vs non-empty canvas. */
const fake = vi.hoisted(() => ({
  elements: [{ id: 'rect-1' }] as unknown[],
  api: {
    getSceneElements: () => fake.elements,
    getAppState: () => ({ viewBackgroundColor: '#ffffff' }),
    getFiles: () => ({}),
    resetScene: vi.fn(() => { fake.elements = [] }),
    setActiveTool: vi.fn(),
    scrollToContent: vi.fn(),
    updateScene: vi.fn((scene: { elements: unknown[] }) => { fake.elements = scene.elements }),
  },
  convertToExcalidrawElements: vi.fn((skeleton: object[]) => skeleton.map(s => ({ ...s, converted: true }))),
  exportToBlob: vi.fn(async () => new Blob(['png-bytes'], { type: 'image/png' })),
  serializeAsJSON: vi.fn(() =>
    JSON.stringify({ type: 'excalidraw', elements: fake.elements, appState: {}, files: {} })),
  restore: vi.fn((data: { elements?: unknown[]; appState?: object; files?: object }) => ({
    elements: data.elements ?? [],
    appState: { ...(data.appState ?? {}), normalized: true },
    files: data.files ?? {},
  })),
}))

vi.mock('@excalidraw/excalidraw', async () => {
  const React = await import('react')
  return {
    Excalidraw: (props: {
      excalidrawAPI?: (api: unknown) => void
      onChange?: () => void
      renderTopRightUI?: () => React.ReactNode
      initialData?:
        | { elements?: unknown[]; files?: Record<string, unknown>; appState?: Record<string, unknown> }
        | (() => { elements?: unknown[]; files?: Record<string, unknown>; appState?: Record<string, unknown> } | null)
        | null
    }) => {
      lastInitialData =
        typeof props.initialData === 'function' ? props.initialData() : props.initialData ?? null
      React.useEffect(() => {
        props.excalidrawAPI?.(fake.api)
        props.onChange?.()
        // Registration + first change fire once per mount, mirroring the real
        // component's startup sequence.
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [])
      return React.createElement('div', { 'data-testid': 'fake-excalidraw' },
        props.renderTopRightUI ? props.renderTopRightUI() : null)
    },
    exportToBlob: fake.exportToBlob,
    serializeAsJSON: fake.serializeAsJSON,
    restore: fake.restore,
    convertToExcalidrawElements: fake.convertToExcalidrawElements,
  }
})
vi.mock('@excalidraw/excalidraw/index.css', () => ({}))

describe('SketchDialog', () => {
  beforeEach(() => {
    fake.elements = [{ id: 'rect-1' }]
    fake.exportToBlob.mockClear()
    fake.serializeAsJSON.mockClear()
  })

  it('renders the whiteboard and enables Insert once the scene has elements', async () => {
    render(<SketchDialog open onOpenChange={() => {}} onInsert={() => {}} />)
    await screen.findByTestId('fake-excalidraw')
    const insert = screen.getByRole('button', { name: 'Attach to message' })
    await waitFor(() => expect(insert).not.toBeDisabled())
  })

  it('keeps Insert disabled while the canvas is empty', async () => {
    fake.elements = []
    render(<SketchDialog open onOpenChange={() => {}} onInsert={() => {}} />)
    await screen.findByTestId('fake-excalidraw')
    expect(screen.getByRole('button', { name: 'Attach to message' })).toBeDisabled()
  })

  it('exports PNG + .excalidraw.json sidecar and closes on Insert', async () => {
    const onInsert = vi.fn()
    const onOpenChange = vi.fn()
    render(<SketchDialog open onOpenChange={onOpenChange} onInsert={onInsert} />)
    await screen.findByTestId('fake-excalidraw')
    const insert = screen.getByRole('button', { name: 'Attach to message' })
    await waitFor(() => expect(insert).not.toBeDisabled())

    fireEvent.click(insert)

    await waitFor(() => expect(onInsert).toHaveBeenCalledTimes(1))
    const files = onInsert.mock.calls[0][0] as File[]
    expect(files).toHaveLength(2)
    expect(files[0].name).toMatch(/^sketch-.+\.png$/)
    expect(files[0].type).toBe('image/png')
    expect(files[1].name).toMatch(/^sketch-.+\.excalidraw$/)
    expect(files[1].type).toBe('application/json')
    // Both artifacts stamp the SAME moment so they pair up in the attachment list.
    expect(files[1].name.replace(/\.excalidraw$/, '')).toBe(files[0].name.replace(/\.png$/, ''))
    expect(fake.exportToBlob).toHaveBeenCalledWith(
      expect.objectContaining({ mimeType: 'image/png', appState: expect.objectContaining({ exportBackground: true }) }),
    )
    expect(onOpenChange).toHaveBeenCalledWith(false)
    // The scene deliberately survives insert: onInsert returns before the
    // upload is accepted, so clearing here would strand a failed upload with
    // no copy to retry from. "New sketch" is the explicit clear path.
  })

  it('surfaces a failure line and stays open when export rejects', async () => {
    fake.exportToBlob.mockRejectedValueOnce(new Error('boom'))
    const onInsert = vi.fn()
    const onOpenChange = vi.fn()
    render(<SketchDialog open onOpenChange={onOpenChange} onInsert={onInsert} />)
    await screen.findByTestId('fake-excalidraw')
    const insert = screen.getByRole('button', { name: 'Attach to message' })
    await waitFor(() => expect(insert).not.toBeDisabled())

    fireEvent.click(insert)

    await screen.findByRole('alert')
    expect(onInsert).not.toHaveBeenCalled()
    expect(onOpenChange).not.toHaveBeenCalled()
    // Insert stays usable for the retry.
    expect(insert).not.toBeDisabled()
  })

  it('persists the scene to localStorage and seeds a fresh mount from it', async () => {
    vi.useFakeTimers()
    try {
      localStorage.removeItem('mc-sketch-scene')
      const { unmount } = render(<SketchDialog open onOpenChange={() => {}} onInsert={() => {}} />)
      // findByTestId under fake timers: the lazy mock resolves on microtasks,
      // so flush them explicitly instead of waiting on real time.
      await vi.waitFor(() => expect(screen.queryByTestId('fake-excalidraw')).not.toBeNull())
      // The mock fires one onChange on mount; the debounced write lands 500ms later.
      vi.advanceTimersByTime(600)
      const stored = JSON.parse(localStorage.getItem('mc-sketch-scene') ?? 'null')
      expect(stored?.elements).toHaveLength(1)
      unmount()

      // A fresh mount (fresh sceneRef — simulating a reload) seeds from storage.
      render(<SketchDialog open onOpenChange={() => {}} onInsert={() => {}} />)
      await vi.waitFor(() => expect(screen.queryByTestId('fake-excalidraw')).not.toBeNull())
      expect(lastInitialData?.elements).toHaveLength(1)
    } finally {
      vi.useRealTimers()
      localStorage.removeItem('mc-sketch-scene')
    }
  })

  it('New sketch resets the canvas and drops the stored draft', async () => {
    localStorage.setItem('mc-sketch-scene', '{"type":"excalidraw","elements":[{"id":"old"}]}')
    render(<SketchDialog open onOpenChange={() => {}} onInsert={() => {}} />)
    await screen.findByTestId('fake-excalidraw')
    const reset = screen.getByRole('button', { name: 'New sketch' })
    await waitFor(() => expect(reset).not.toBeDisabled())

    // Two-step confirm: first click arms, second click executes.
    fireEvent.click(reset)
    expect(fake.api.resetScene).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Discard drawing' }))

    expect(fake.api.resetScene).toHaveBeenCalled()
    expect(localStorage.getItem('mc-sketch-scene')).toBeNull()
    // Attach disables again on the now-empty canvas.
    expect(screen.getByRole('button', { name: 'Attach to message' })).toBeDisabled()
  })

  it('does not mount Excalidraw while closed (lazy chunk stays unloaded)', () => {
    render(<SketchDialog open={false} onOpenChange={() => {}} onInsert={() => {}} />)
    expect(screen.queryByTestId('fake-excalidraw')).toBeNull()
  })
})

describe('SketchDialog — annotate mode', () => {
  const background = { dataUrl: 'data:image/png;base64,AAAA', width: 1200, height: 800, exportScale: 2 }

  beforeEach(() => {
    // The scene starts as the locked background alone: nothing drawn yet.
    fake.elements = [{ id: 'kc-annotate-bg', type: 'image' }]
    fake.exportToBlob.mockClear()
    fake.serializeAsJSON.mockClear()
    fake.api.setActiveTool.mockClear()
    fake.api.scrollToContent.mockClear()
    fake.api.updateScene.mockClear()
    fake.api.resetScene.mockClear()
    localStorage.removeItem('mc-sketch-scene')
  })

  it('seeds the scene with the screenshot as a LOCKED image at origin sized to the CSS viewport', async () => {
    render(<SketchDialog open onOpenChange={() => {}} onInsert={() => {}} background={background} />)
    await screen.findByTestId('fake-excalidraw')
    expect(fake.convertToExcalidrawElements).toHaveBeenCalledWith(
      [expect.objectContaining({ type: 'image', id: 'kc-annotate-bg', x: 0, y: 0, width: 1200, height: 800, fileId: 'kc-annotate-bg', locked: true })],
      { regenerateIds: false },
    )
    expect(lastInitialData?.files?.['kc-annotate-bg']).toEqual(expect.objectContaining({ mimeType: 'image/png', dataURL: background.dataUrl }))
    // Red clean strokes, not the sketch pad's hand-drawn default.
    expect(lastInitialData?.appState).toEqual(expect.objectContaining({ currentItemStrokeColor: '#e03131', currentItemRoughness: 0 }))
    // Lands on the rectangle tool with the screenshot fitted.
    expect(fake.api.setActiveTool).toHaveBeenCalledWith({ type: 'rectangle' })
    // The fit is deferred until the canvas has a size.
    await waitFor(() => expect(fake.api.scrollToContent).toHaveBeenCalledWith(undefined, expect.objectContaining({ fitToViewport: true })))
    expect(screen.getByText('Annotate screenshot')).toBeInTheDocument()
    expect(screen.getByTestId('annotate-dialog')).toBeInTheDocument()
  })

  it('the background alone does not count as something to send', async () => {
    render(<SketchDialog open onOpenChange={() => {}} onInsert={() => {}} background={background} />)
    await screen.findByTestId('fake-excalidraw')
    expect(screen.getByRole('button', { name: 'Send to chat' })).toBeDisabled()
  })

  it('Send to chat exports one padding-free PNG at the capture DPR and hands the scene back', async () => {
    fake.elements = [{ id: 'kc-annotate-bg', type: 'image' }, { id: 'r1', type: 'rectangle', x: 1, y: 2, width: 3, height: 4 }]
    const onInsert = vi.fn()
    const onOpenChange = vi.fn()
    render(<SketchDialog open onOpenChange={onOpenChange} onInsert={onInsert} background={background} />)
    await screen.findByTestId('fake-excalidraw')
    const send = screen.getByRole('button', { name: 'Send to chat' })
    await waitFor(() => expect(send).not.toBeDisabled())
    fireEvent.click(send)
    await waitFor(() => expect(onInsert).toHaveBeenCalledTimes(1))
    const [files, scene] = onInsert.mock.calls[0] as [File[], { elements: unknown[] }]
    expect(files).toHaveLength(1)
    expect(files[0].name).toMatch(/^browser-annotation-.+\.png$/)
    expect(scene.elements).toBe(fake.elements)
    expect(fake.exportToBlob).toHaveBeenCalledWith(expect.objectContaining({
      exportPadding: 0,
      appState: expect.objectContaining({ exportBackground: true, exportWithDarkMode: false, exportScale: 2 }),
    }))
    // No .excalidraw sidecar and no draft persistence in annotate mode.
    expect(fake.serializeAsJSON).not.toHaveBeenCalled()
    expect(localStorage.getItem('mc-sketch-scene')).toBeNull()
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('⌘/Ctrl+Enter sends', async () => {
    fake.elements = [{ id: 'kc-annotate-bg', type: 'image' }, { id: 'r1', type: 'rectangle', x: 1, y: 2, width: 3, height: 4 }]
    const onInsert = vi.fn()
    render(<SketchDialog open onOpenChange={() => {}} onInsert={onInsert} background={background} />)
    await screen.findByTestId('fake-excalidraw')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Send to chat' })).not.toBeDisabled())
    fireEvent.keyDown(screen.getByTestId('fake-excalidraw'), { key: 'Enter', metaKey: true })
    await waitFor(() => expect(onInsert).toHaveBeenCalledTimes(1))
    // Plain Enter is Excalidraw's own key (edit text) and must not send.
    fireEvent.keyDown(screen.getByTestId('fake-excalidraw'), { key: 'Enter' })
    expect(onInsert).toHaveBeenCalledTimes(1)
  })

  it('Clear marks keeps the screenshot and removes only the drawing', async () => {
    fake.elements = [{ id: 'kc-annotate-bg', type: 'image' }, { id: 'r1', type: 'rectangle', x: 1, y: 2, width: 3, height: 4 }]
    render(<SketchDialog open onOpenChange={() => {}} onInsert={() => {}} background={background} />)
    await screen.findByTestId('fake-excalidraw')
    const clear = screen.getByRole('button', { name: 'Clear marks' })
    await waitFor(() => expect(clear).not.toBeDisabled())
    fireEvent.click(clear)
    fireEvent.click(screen.getByRole('button', { name: 'Discard drawing' }))
    expect(fake.api.updateScene).toHaveBeenCalledWith({ elements: [{ id: 'kc-annotate-bg', type: 'image' }] })
    expect(fake.api.resetScene).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Send to chat' })).toBeDisabled()
  })
})
