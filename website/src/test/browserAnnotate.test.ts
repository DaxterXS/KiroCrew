import { describe, expect, it } from 'vitest'
import {
  ANNOTATE_BG_ID,
  MIN_COVERAGE,
  buildAnnotationFiles,
  marksFromScene,
  matchMark,
  type AnnotateElement,
  type SceneElementLike,
} from '../utils/browserAnnotate'
import { formatAnnotationLine, formatAnnotationNote } from '../utils/browserAnnotate.prompt'

const el = (ref: string, x: number, y: number, w: number, h: number, extra: Partial<AnnotateElement> = {}): AnnotateElement => ({
  ref, role: 'button', name: ref, selector: `#${ref}`, rect: { x, y, width: w, height: h }, ...extra,
})

const bg: SceneElementLike = { id: ANNOTATE_BG_ID, type: 'image', x: 0, y: 0, width: 1200, height: 800 }

describe('marksFromScene', () => {
  it('drops the background image and deleted elements, keeps drawing order', () => {
    const marks = marksFromScene([
      bg,
      { id: 'r1', type: 'rectangle', x: 10, y: 20, width: 100, height: 40 },
      { id: 'gone', type: 'ellipse', x: 0, y: 0, width: 10, height: 10, isDeleted: true },
      { id: 'e1', type: 'ellipse', x: 300, y: 300, width: 50, height: 50 },
    ])
    expect(marks.map(m => m.kind)).toEqual(['rectangle', 'ellipse'])
    expect(marks[0].box).toEqual({ x: 10, y: 20, width: 100, height: 40 })
  })

  it('normalises a shape dragged up-left (negative width/height)', () => {
    const [m] = marksFromScene([{ id: 'r', type: 'rectangle', x: 110, y: 60, width: -100, height: -40 }])
    expect(m.box).toEqual({ x: 10, y: 20, width: 100, height: 40 })
  })

  it('folds text bound to a container into that shape as its label', () => {
    const marks = marksFromScene([
      { id: 'r1', type: 'rectangle', x: 0, y: 0, width: 80, height: 30 },
      { id: 't1', type: 'text', x: 5, y: 5, width: 60, height: 20, text: ' this one ', containerId: 'r1' },
    ])
    expect(marks).toHaveLength(1)
    expect(marks[0].label).toBe('this one')
  })

  it('keeps free-standing text as its own mark and skips empty text', () => {
    const marks = marksFromScene([
      { id: 't1', type: 'text', x: 5, y: 5, width: 60, height: 20, text: 'wrong colour' },
      { id: 't2', type: 'text', x: 5, y: 50, width: 60, height: 20, text: '   ' },
    ])
    expect(marks).toEqual([{ kind: 'text', box: { x: 5, y: 5, width: 60, height: 20 }, label: 'wrong colour' }])
  })

  it('reports an arrow tip at its last point and a bbox over all points', () => {
    const [m] = marksFromScene([{
      id: 'a', type: 'arrow', x: 100, y: 100, width: 50, height: 30, points: [[0, 0], [20, -10], [50, 30]],
    }])
    expect(m.kind).toBe('arrow')
    expect(m.tip).toEqual({ x: 150, y: 130 })
    expect(m.box).toEqual({ x: 100, y: 90, width: 50, height: 40 })
  })

  it('treats diamond as rectangle and line as arrow; ignores unknown types', () => {
    const marks = marksFromScene([
      { id: 'd', type: 'diamond', x: 0, y: 0, width: 10, height: 10 },
      { id: 'l', type: 'line', x: 0, y: 0, width: 10, height: 0, points: [[0, 0], [10, 0]] },
      { id: 'f', type: 'frame', x: 0, y: 0, width: 10, height: 10 },
    ])
    expect(marks.map(m => m.kind)).toEqual(['rectangle', 'arrow'])
  })
})

describe('matchMark', () => {
  const elements = [
    el('e1', 0, 0, 1200, 60, { role: 'link', name: 'Header' }),     // wide bar
    el('e2', 100, 200, 120, 40, { name: 'Save' }),                  // button
    el('e3', 100, 300, 120, 40, { name: 'Cancel' }),                // sibling below
    el('e4', 500, 200, 400, 300, { role: 'textbox', name: 'Body' }), // large field
  ]

  it('picks the element the box covers most (rectangle around a button)', () => {
    const [m] = marksFromScene([{ id: 'r', type: 'rectangle', x: 90, y: 190, width: 140, height: 60 }])
    const r = matchMark(m, elements)
    expect(r.element?.ref).toBe('e2')
    expect(r.coverage).toBe(1)
  })

  it('needs at least MIN_COVERAGE of an element, else falls back to the element under the centre', () => {
    // A small box drawn INSIDE the big textbox: coverage of e4 is tiny, so the
    // centre-hit fallback must still name e4 rather than nothing.
    const [m] = marksFromScene([{ id: 'r', type: 'rectangle', x: 600, y: 300, width: 40, height: 20 }])
    const r = matchMark(m, elements)
    expect(r.element?.ref).toBe('e4')
    expect(r.coverage).toBeLessThan(MIN_COVERAGE)
  })

  it('prefers the element that fills more of the box when coverage ties', () => {
    // Box spans both buttons fully (coverage 1 each); e2 and e3 tie, and the
    // tie-break is fill, which is equal too — so it must pick deterministically
    // the first best (e2) rather than flip-flopping.
    const [m] = marksFromScene([{ id: 'r', type: 'rectangle', x: 90, y: 190, width: 140, height: 160 }])
    expect(matchMark(m, elements).element?.ref).toBe('e2')
  })

  it('maps an arrow by its tip, choosing the smallest containing element', () => {
    const [m] = marksFromScene([{
      id: 'a', type: 'arrow', x: 20, y: 500, width: 0, height: 0, points: [[0, 0], [140, -280]],
    }])
    expect(m.tip).toEqual({ x: 160, y: 220 })
    expect(matchMark(m, elements).element?.ref).toBe('e2')
  })

  it('returns null when nothing is under the mark', () => {
    const [m] = marksFromScene([{ id: 'r', type: 'ellipse', x: 1000, y: 700, width: 20, height: 20 }])
    const r = matchMark(m, elements)
    expect(r.element).toBeNull()
    expect(r.coverage).toBe(0)
  })

  it('maps a text label by its centre', () => {
    const [m] = marksFromScene([{ id: 't', type: 'text', x: 110, y: 210, width: 60, height: 20, text: 'here' }])
    expect(matchMark(m, elements).element?.ref).toBe('e2')
  })
})

describe('annotation note', () => {
  it('names ref, role, name, selector and the mark for a matched box', () => {
    const [m] = marksFromScene([{ id: 'r', type: 'rectangle', x: 90, y: 190, width: 140, height: 60 }])
    const line = formatAnnotationLine(1, matchMark(m, [el('e2', 100, 200, 120, 40, { name: 'Save' })]))
    expect(line).toContain('1. box')
    expect(line).toContain('button "Save" [ref=e2]')
    expect(line).toContain('selector `#e2`')
    expect(line).toContain('at (90, 190) 140×60')
    expect(line).toContain('(coverage 1.00)')
  })

  it('says so when no element is under an arrow, with the tip coordinates', () => {
    const [m] = marksFromScene([{ id: 'a', type: 'arrow', x: 5, y: 5, width: 0, height: 0, points: [[0, 0], [10, 10]] }])
    const line = formatAnnotationLine(2, matchMark(m, []))
    expect(line).toBe('2. arrow — tip at (15, 15) — no interactive element under it')
  })

  it('renders a self-contained document with page, viewport, image name and every mark', () => {
    const note = formatAnnotationNote(
      [matchMark(marksFromScene([{ id: 't', type: 'text', x: 1, y: 1, width: 5, height: 5, text: 'hi' }])[0], [])],
      { url: 'https://x.test/p', title: 'Page', cssWidth: 1200, cssHeight: 800, imageName: 'browser-annotation-1.png' },
    )
    expect(note).toContain('# Browser annotation')
    expect(note).toContain('Page: Page — https://x.test/p')
    expect(note).toContain('1200×800 CSS px')
    expect(note).toContain('`browser-annotation-1.png`')
    expect(note).toContain('1. text "hi"')
    expect(note).toContain('`snapshot`')
  })

  it('states when there are no marks at all', () => {
    const note = formatAnnotationNote([], { url: '', title: '', cssWidth: 1, cssHeight: 1, imageName: 'a.png' })
    expect(note).toContain('No marks')
    expect(note).toContain('(unknown url)')
  })
})

describe('buildAnnotationFiles', () => {
  it('returns the PNG untouched plus a Markdown sidecar sharing its stamp', async () => {
    const png = new File([new Uint8Array([1, 2, 3])], 'browser-annotation-2026-01-02T03-04-05.png', { type: 'image/png' })
    const { files, note, matches } = buildAnnotationFiles(
      png,
      [bg, { id: 'r', type: 'rectangle', x: 90, y: 190, width: 140, height: 60 }],
      { elements: [el('e2', 100, 200, 120, 40, { name: 'Save' })], url: 'https://x.test', title: 'T', cssWidth: 1200, cssHeight: 800 },
    )
    expect(files[0]).toBe(png)
    expect(files[1].name).toBe('browser-annotation-2026-01-02T03-04-05.md')
    expect(files[1].type).toBe('text/markdown')
    expect(await files[1].text()).toBe(note)
    expect(matches[0].element?.ref).toBe('e2')
    expect(note).toContain('[ref=e2]')
  })

  it('still produces a sidecar when the capture metadata is missing', () => {
    const png = new File([''], 'x.png', { type: 'image/png' })
    const { files, matches } = buildAnnotationFiles(png, [{ id: 'r', type: 'rectangle', x: 0, y: 0, width: 5, height: 5 }], null)
    expect(files).toHaveLength(2)
    expect(matches[0].element).toBeNull()
  })
})
