/**
 * Renders the Annotate sidecar the AGENT reads next to the annotated PNG.
 *
 * Model-facing text, not user-visible copy (hence the `.prompt.ts` boundary):
 * the `eN` refs, roles and selectors are identifiers the agent matches on and
 * passes straight back to the `browser` tool, so the note is English by design
 * and is never rendered in the dashboard.
 */
import type { MarkMatch } from './browserAnnotate'

export interface AnnotationNoteMeta {
  url: string
  title: string
  cssWidth: number
  cssHeight: number
  /** File name of the annotated PNG the note accompanies. */
  imageName: string
}

const KIND_WORD: Record<MarkMatch['mark']['kind'], string> = {
  rectangle: 'box',
  ellipse: 'circle',
  arrow: 'arrow',
  freedraw: 'freehand mark',
  text: 'text',
}

function fmtRect(r: { x: number; y: number; width: number; height: number }): string {
  // getBoundingClientRect yields sub-pixel values; whole CSS px is what a
  // reader (or a click) needs.
  return `(${Math.round(r.x)}, ${Math.round(r.y)}) ${Math.round(r.width)}×${Math.round(r.height)}`
}

function fmtName(name: string): string {
  return name ? ` "${name.replace(/\s+/g, ' ').trim()}"` : ''
}

/** One numbered line per mark, drawing order. */
export function formatAnnotationLine(index: number, m: MarkMatch): string {
  const { mark, element } = m
  const head = `${index}. ${KIND_WORD[mark.kind]}${mark.label ? ` "${mark.label}"` : ''}`
  const where = mark.kind === 'arrow' && mark.tip
    ? `tip at (${mark.tip.x}, ${mark.tip.y})`
    : `at ${fmtRect(mark.box)}`
  if (!element) {
    return `${head} — ${where} — no interactive element under it`
  }
  // A bare ratio, not a percentage: this is machine-facing data for the agent,
  // and the i18n unit-literal scanner (rightly) refuses number+unit strings.
  const cov = mark.kind === 'rectangle' || mark.kind === 'ellipse' || mark.kind === 'freedraw'
    ? ` (coverage ${m.coverage.toFixed(2)})`
    : ''
  const sel = element.selector ? ` · selector \`${element.selector}\`` : ''
  return `${head} → ${element.role}${fmtName(element.name)} [ref=${element.ref}]${sel} · element at ${fmtRect(element.rect)} — ${where}${cov}`
}

/**
 * The whole sidecar as Markdown. Self-contained: a reader with only this file
 * and the PNG knows which page, which viewport, and how to act on each ref.
 */
export function formatAnnotationNote(matches: readonly MarkMatch[], meta: AnnotationNoteMeta): string {
  const lines: string[] = []
  lines.push('# Browser annotation')
  lines.push('')
  lines.push(`Page: ${meta.title ? `${meta.title} — ` : ''}${meta.url || '(unknown url)'}`)
  lines.push(`Viewport: ${meta.cssWidth}×${meta.cssHeight} CSS px. The attached image \`${meta.imageName}\` is this viewport with the user's marks drawn on it; coordinates below are CSS px in that image.`)
  lines.push('')
  lines.push(
    'Each mark is mapped to the interactive element under it. `ref` values are the built-in Browser panel\'s element refs — the same `eN` the `browser` tool\'s `snapshot` returns — so they can be passed to `click` / `type` / `hover` directly (re-run `snapshot` first if the page has changed).',
  )
  lines.push('')
  if (!matches.length) {
    lines.push('_No marks — the screenshot was sent without annotations._')
  } else {
    matches.forEach((m, i) => lines.push(formatAnnotationLine(i + 1, m)))
  }
  lines.push('')
  return lines.join('\n')
}
