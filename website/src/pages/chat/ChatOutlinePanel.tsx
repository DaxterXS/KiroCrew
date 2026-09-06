import { memo, useState, type KeyboardEvent } from 'react'
import { i18nT } from '../../i18n/t'
import { useLanguageGeneration } from '../../i18n/useLanguageGeneration'
import type { ChatMessage } from '../../types'

/** One outline entry: a user turn addressable by the same identity the jump
 *  machinery already resolves (`mid`, with `ts` as the legacy fallback). */
export interface OutlineEntry {
  /** Server-minted row id (`meta.mid`); undefined only for a not-yet-persisted
   *  turn, in which case the jump falls back to `ts`, exactly as the pins jump
   *  does. */
  mid?: string
  /** Message timestamp — the jump's fallback key and the highlight key. */
  ts?: string
  /** Truncated prompt text shown in the list. */
  preview: string
}

const PREVIEW_MAX = 120

/** Collapse a user prompt to a single trimmed line for the outline list.
 *  Whitespace (including the newlines a multi-line prompt carries) is collapsed
 *  so a row is one scannable line; over-length text is cut and ellipsised. The
 *  visible truncation is a belt to `line-clamp-1`'s braces: the DOM text stays
 *  short too, so a 50KB paste never lands in the list node. */
export function outlinePreview(content: string): string {
  const oneLine = content.replace(/\s+/g, ' ').trim()
  if (oneLine.length <= PREVIEW_MAX) return oneLine
  return oneLine.slice(0, PREVIEW_MAX).trimEnd() + '\u2026'
}

/** Project the transcript to the user turns that become outline rows.
 *  Kept pure and exported so a test pins the projection without a store. A turn
 *  with neither `mid` nor `ts` is dropped: the jump has nothing to resolve it
 *  by, so an unclickable row would be a dead entry. Empty prompts are dropped
 *  for the same reason a blank row helps no one navigate. */
export function outlineEntries(messages: ChatMessage[]): OutlineEntry[] {
  const out: OutlineEntry[] = []
  for (const m of messages) {
    if (m.role !== 'user') continue
    const mid = typeof m.meta?.mid === 'string' && m.meta.mid ? m.meta.mid : undefined
    const ts = m.ts
    if (!mid && !ts) continue
    const preview = outlinePreview(m.content ?? '')
    if (!preview) continue
    out.push({ mid, ts, preview })
  }
  return out
}

interface ChatOutlinePanelProps {
  /** User turns to list, in transcript order. */
  entries: OutlineEntry[]
  /** Jump to a loaded turn — the SAME generic jump the pins list uses
   *  (`(messageTs, mid?) => void`), so scrolling and the 3s highlight are
   *  inherited rather than reinvented. */
  onJumpToMessage: (messageTs: string, mid?: string) => void
}

/**
 * Body of the side panel's Outline tab: a table-of-contents of the current
 * session's user turns. Clicking (or activating with Enter/Space) an entry
 * scrolls to and highlights that turn via the existing jump path.
 *
 * Chrome-less like the sibling Pins tab: the tab strip already names this view
 * and owns closing it, so there is no header or close button here, and it does
 * not grab focus on mount (see PinnedMessagesPanel's note on the panel's
 * return-focus contract).
 *
 * Rows are real <button>s inside a role="list", so the outline is reachable and
 * operable by keyboard by construction, and the last-activated entry carries
 * `aria-current="true"` so a screen reader conveys the user's place in the list
 * rather than leaving it to styling alone. That current marker tracks the entry
 * the user last jumped to; live "which turn is on screen now" tracking as the
 * user scrolls is deliberately out of scope for this first version (see the PR
 * body's follow-on scope).
 */
const ChatOutlinePanel = memo(function ChatOutlinePanel({
  entries,
  onJumpToMessage,
}: ChatOutlinePanelProps) {
  useLanguageGeneration() // memo() bails out of the provider-level repaint; subscribe directly

  // Which entry the user last activated. Identity is the row's mid (falling
  // back to ts), matching the jump's own resolution order, so aria-current
  // marks the same row the jump targeted. Not scroll-derived — see the class
  // docstring.
  const [currentKey, setCurrentKey] = useState<string | null>(null)

  const entryKey = (e: OutlineEntry): string => e.mid ?? e.ts ?? ''

  const activate = (e: OutlineEntry) => {
    setCurrentKey(entryKey(e))
    // ts is the highlight key downstream; pass '' when a turn only has a mid so
    // the signature is satisfied, exactly as the pins jump tolerates a missing
    // ts when a mid is present.
    onJumpToMessage(e.ts ?? '', e.mid)
  }

  const onKeyDown = (ev: KeyboardEvent<HTMLButtonElement>, e: OutlineEntry) => {
    // Enter and Space are the native <button> activation keys; Space would
    // otherwise scroll the list, so claim it explicitly.
    if (ev.key === ' ' || ev.key === 'Spacebar') {
      ev.preventDefault()
      activate(e)
    }
  }

  return (
    <div
      role="region"
      aria-label={i18nT('pages.chat.outline.outline')}
      className="flex flex-col h-full bg-bg"
      data-testid="chat-outline-panel"
    >
      <div className="flex-1 overflow-y-auto px-3 py-2">
        {entries.length === 0 && (
          <div className="text-muted text-sm text-center py-8" data-testid="chat-outline-empty-state">
            {i18nT('pages.chat.outline.no_turns')}
          </div>
        )}
        {entries.length > 0 && (
          <ul className="flex flex-col">
            {entries.map((e, i) => {
              const key = entryKey(e)
              const isCurrent = currentKey !== null && key === currentKey
              return (
                <li key={key || i}>
                  <button
                    type="button"
                    onClick={() => activate(e)}
                    onKeyDown={(ev) => onKeyDown(ev, e)}
                    aria-current={isCurrent ? 'true' : undefined}
                    data-testid="chat-outline-entry"
                    data-current={isCurrent ? 'true' : undefined}
                    className={`w-full text-left flex items-start gap-2 px-3 py-2 rounded-md cursor-pointer transition-colors mb-0.5 hover:bg-bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${isCurrent ? 'bg-bg-hover text-text' : 'text-text'}`}
                  >
                    <span className="text-[11px] text-muted tabular-nums pt-0.5 select-none w-6 shrink-0 text-right">
                      {i + 1}
                    </span>
                    <span className="text-sm leading-snug line-clamp-1 min-w-0">
                      {e.preview}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
})

export { ChatOutlinePanel }
export type { ChatOutlinePanelProps }
