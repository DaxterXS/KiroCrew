/**
 * Browser-panel Annotate: geometry only.
 *
 * The user draws on a viewport screenshot inside the sketch pad (Excalidraw).
 * This module turns the resulting scene into marks in screenshot CSS-px space
 * and maps each mark to the interactive element under it, using the element
 * rects the Annotate capture took alongside the screenshot. Everything here is
 * pure and DOM-free so it is unit-testable; the agent-facing note is rendered
 * by `browserAnnotate.prompt.ts`, and the File plumbing lives in the panel.
 *
 * Coordinate contract: the background screenshot is laid out as an Excalidraw
 * image element at scene (0,0) with width/height equal to the CSS viewport
 * size, so scene coordinates ARE CSS px of the page. No scaling is needed here;
 * the capture's `dpr` only affects the exported PNG's pixel density.
 */
import { formatAnnotationNote } from './browserAnnotate.prompt'

/** Element id of the locked background screenshot in the annotate scene. */
export const ANNOTATE_BG_ID = 'kc-annotate-bg'

/** Window event: the panel hands a finished annotation (PNG + note sidecar) to
 *  ChatPage, which owns the upload → attachments pipeline. Same shape of hand-
 *  off as PREVIEW_SNIP_EVENT, but the files are already rendered. */
export const PREVIEW_ANNOTATE_EVENT = 'kirocrew-web-preview-annotate'

export interface AnnotateRect {
  x: number
  y: number
  width: number
  height: number
}

/** One interactive element from the capture (mirrors BrowserAnnotateElement). */
export interface AnnotateElement {
  ref: string
  role: string
  name: string
  selector: string
  rect: AnnotateRect
}

export type MarkKind = 'rectangle' | 'ellipse' | 'arrow' | 'freedraw' | 'text'

export interface AnnotationMark {
  kind: MarkKind
  /** Bounding box in screenshot CSS px (integers). */
  box: AnnotateRect
  /** Where the arrow points (arrows only). */
  tip?: { x: number; y: number }
  /** The mark's own text, or the label bound to the shape. Empty when none. */
  label: string
}

export interface MarkMatch {
  mark: AnnotationMark
  element: AnnotateElement | null
  /** Fraction of the element's area the mark covers (0..1); 1 for point hits. */
  coverage: number
}

/** The subset of an Excalidraw element this module reads. Structural on
 *  purpose: the scene comes straight from `api.getSceneElements()`, and a
 *  narrow shape keeps the mapping testable without the library. */
export interface SceneElementLike {
  id: string
  type: string
  x: number
  y: number
  width: number
  height: number
  isDeleted?: boolean
  /** Linear/freedraw: points relative to (x, y). */
  points?: readonly (readonly [number, number])[] | readonly number[][]
  text?: string
  /** Text bound inside a container (or attached to an arrow). */
  containerId?: string | null
}

const round = (n: number) => Math.round(n)

/** Normalise a possibly negative-sized box into positive width/height. */
function normalizeBox(x: number, y: number, w: number, h: number): AnnotateRect {
  const nx = w < 0 ? x + w : x
  const ny = h < 0 ? y + h : y
  return { x: round(nx), y: round(ny), width: round(Math.abs(w)), height: round(Math.abs(h)) }
}

function pointsBox(el: SceneElementLike): AnnotateRect {
  const pts = el.points ?? []
  if (!pts.length) return normalizeBox(el.x, el.y, el.width, el.height)
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const p of pts) {
    const px = el.x + (p[0] ?? 0)
    const py = el.y + (p[1] ?? 0)
    if (px < minX) minX = px
    if (py < minY) minY = py
    if (px > maxX) maxX = px
    if (py > maxY) maxY = py
  }
  return normalizeBox(minX, minY, maxX - minX, maxY - minY)
}

function kindOf(type: string): MarkKind | null {
  switch (type) {
    case 'rectangle':
    case 'diamond':
      return 'rectangle'
    case 'ellipse':
      return 'ellipse'
    case 'arrow':
    case 'line':
      return 'arrow'
    case 'freedraw':
      return 'freedraw'
    case 'text':
      return 'text'
    default:
      return null
  }
}

/**
 * Convert the annotate scene into marks, in drawing order. The background
 * image (and any other image) is skipped; text bound to a shape becomes that
 * shape's label instead of a mark of its own.
 */
export function marksFromScene(
  elements: readonly SceneElementLike[],
  bgId: string = ANNOTATE_BG_ID,
): AnnotationMark[] {
  const live = elements.filter(e => e && !e.isDeleted && e.id !== bgId)
  const ids = new Set(live.map(e => e.id))
  const labels = new Map<string, string>()
  for (const e of live) {
    if (e.type === 'text' && e.containerId && ids.has(e.containerId)) {
      const t = (e.text ?? '').trim()
      if (t) labels.set(e.containerId, labels.has(e.containerId) ? `${labels.get(e.containerId)} ${t}` : t)
    }
  }
  const out: AnnotationMark[] = []
  for (const e of live) {
    const kind = kindOf(e.type)
    if (!kind) continue
    if (kind === 'text') {
      if (e.containerId && ids.has(e.containerId)) continue // consumed as a label
      const t = (e.text ?? '').trim()
      if (!t) continue
      out.push({ kind, box: normalizeBox(e.x, e.y, e.width, e.height), label: t })
      continue
    }
    if (kind === 'arrow') {
      const pts = e.points ?? []
      const last = pts.length ? pts[pts.length - 1] : null
      const tip = last ? { x: round(e.x + (last[0] ?? 0)), y: round(e.y + (last[1] ?? 0)) } : undefined
      out.push({ kind, box: pointsBox(e), tip, label: labels.get(e.id) ?? '' })
      continue
    }
    if (kind === 'freedraw') {
      out.push({ kind, box: pointsBox(e), label: labels.get(e.id) ?? '' })
      continue
    }
    out.push({ kind, box: normalizeBox(e.x, e.y, e.width, e.height), label: labels.get(e.id) ?? '' })
  }
  return out
}

const area = (r: AnnotateRect) => Math.max(0, r.width) * Math.max(0, r.height)

function intersection(a: AnnotateRect, b: AnnotateRect): number {
  const x1 = Math.max(a.x, b.x)
  const y1 = Math.max(a.y, b.y)
  const x2 = Math.min(a.x + a.width, b.x + b.width)
  const y2 = Math.min(a.y + a.height, b.y + b.height)
  return Math.max(0, x2 - x1) * Math.max(0, y2 - y1)
}

function contains(r: AnnotateRect, p: { x: number; y: number }): boolean {
  return p.x >= r.x && p.x <= r.x + r.width && p.y >= r.y && p.y <= r.y + r.height
}

/** Smallest element whose rect contains the point, or null. */
function hitPoint(p: { x: number; y: number }, elements: readonly AnnotateElement[]): AnnotateElement | null {
  let best: AnnotateElement | null = null
  let bestArea = Infinity
  for (const el of elements) {
    if (!contains(el.rect, p)) continue
    const a = area(el.rect)
    if (a < bestArea) {
      best = el
      bestArea = a
    }
  }
  return best
}

/** A mark must cover at least this much of an element to be "about" it. */
export const MIN_COVERAGE = 0.5

/**
 * Map one mark to the element it most plausibly points at.
 *
 *  • arrow: the element under the arrow head (smallest containing rect).
 *  • text: the element under the text's centre — a caption on top of a button.
 *  • rectangle / ellipse / freedraw: the element whose area the box covers most
 *    (coverage = intersection ÷ element area), ties broken by how much of the
 *    box that element fills, among elements covered ≥ MIN_COVERAGE. A box drawn
 *    INSIDE a large element (coverage below the floor everywhere) falls back to
 *    the smallest element containing the box centre.
 */
export function matchMark(mark: AnnotationMark, elements: readonly AnnotateElement[]): MarkMatch {
  if (mark.kind === 'arrow') {
    const el = mark.tip ? hitPoint(mark.tip, elements) : null
    return { mark, element: el, coverage: el ? 1 : 0 }
  }
  const center = { x: mark.box.x + mark.box.width / 2, y: mark.box.y + mark.box.height / 2 }
  if (mark.kind === 'text') {
    const el = hitPoint(center, elements)
    return { mark, element: el, coverage: el ? 1 : 0 }
  }
  const markArea = area(mark.box)
  let best: AnnotateElement | null = null
  let bestCoverage = 0
  let bestFill = 0
  for (const el of elements) {
    const elArea = area(el.rect)
    if (!elArea) continue
    const inter = intersection(mark.box, el.rect)
    if (!inter) continue
    const coverage = inter / elArea
    const fill = markArea ? inter / markArea : 0
    if (coverage < MIN_COVERAGE) continue
    if (coverage > bestCoverage + 1e-6 || (Math.abs(coverage - bestCoverage) <= 1e-6 && fill > bestFill)) {
      best = el
      bestCoverage = coverage
      bestFill = fill
    }
  }
  if (best) return { mark, element: best, coverage: Math.min(1, bestCoverage) }
  const inside = hitPoint(center, elements)
  if (inside) {
    const cov = area(inside.rect) ? intersection(mark.box, inside.rect) / area(inside.rect) : 0
    return { mark, element: inside, coverage: Math.min(1, cov) }
  }
  return { mark, element: null, coverage: 0 }
}

/** Map every mark of a scene. */
export function matchMarks(marks: readonly AnnotationMark[], elements: readonly AnnotateElement[]): MarkMatch[] {
  return marks.map(m => matchMark(m, elements))
}

/** Local-time stamp shared by the PNG and its sidecar so the pair sorts
 *  together (mirrors SketchDialog's sketch-<ts> naming). */
export function annotationStamp(now: Date = new Date()): string {
  return now.toISOString().replace(/[:.]/g, '-').slice(0, 19)
}

export interface AnnotationCaptureMeta {
  elements: readonly AnnotateElement[]
  url: string
  title: string
  cssWidth: number
  cssHeight: number
}

/**
 * The files the chat receives for one annotation: the exported PNG as-is,
 * plus a Markdown sidecar naming the element under every mark. The sidecar
 * shares the PNG's stamp so the two attachments sort as a pair.
 */
export function buildAnnotationFiles(
  png: File,
  sceneElements: readonly SceneElementLike[],
  meta: AnnotationCaptureMeta | null,
): { files: File[]; note: string; matches: MarkMatch[] } {
  const marks = marksFromScene(sceneElements)
  const matches = matchMarks(marks, meta?.elements ?? [])
  const note = formatAnnotationNote(matches, {
    url: meta?.url ?? '',
    title: meta?.title ?? '',
    cssWidth: meta?.cssWidth ?? 0,
    cssHeight: meta?.cssHeight ?? 0,
    imageName: png.name,
  })
  const stamp = /browser-annotation-(.+)\.png$/.exec(png.name)?.[1] ?? annotationStamp()
  const sidecar = new File([note], `browser-annotation-${stamp}.md`, { type: 'text/markdown' })
  return { files: [png, sidecar], note, matches }
}
