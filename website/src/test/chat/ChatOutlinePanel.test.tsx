/**
 * The chat outline tab lists the session's USER turns and jumps to one on click
 * or keyboard activation, reusing the transcript's existing jump path.
 *
 * Two layers are pinned here:
 *  - `outlineEntries` / `outlinePreview`: the pure projection from the redux
 *    `ChatMessage[]` to outline rows (user-only, id-or-ts required, one trimmed
 *    line). This is what keeps a 50KB paste out of the list DOM and drops rows
 *    the jump could never resolve.
 *  - `ChatOutlinePanel`: that clicking or Space/Enter-activating a row calls the
 *    generic jump with the row's (ts, mid), and that the activated row is the
 *    one carrying aria-current — the screen-reader-perceivable "you are here"
 *    the feature requires, conveyed by more than styling.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ChatOutlinePanel, outlineEntries, outlinePreview } from '../../pages/chat/ChatOutlinePanel'
import type { ChatMessage } from '../../types'

const userMsg = (content: string, mid?: string, ts?: string): ChatMessage => ({
  role: 'user',
  content,
  cls: '',
  ts,
  meta: mid ? { mid } : undefined,
})
const asstMsg = (content: string, ts?: string): ChatMessage => ({ role: 'assistant', content, cls: '', ts })

describe('outlinePreview', () => {
  it('collapses whitespace to one scannable line', () => {
    expect(outlinePreview('  fix   the\n\nbug  ')).toBe('fix the bug')
  })
  it('truncates long text and ellipsises, keeping the DOM node short', () => {
    const long = 'a'.repeat(500)
    const out = outlinePreview(long)
    expect(out.length).toBeLessThan(140)
    expect(out.endsWith('\u2026')).toBe(true)
  })
})

describe('outlineEntries', () => {
  it('keeps only user turns, in order, carrying mid and ts', () => {
    const msgs = [
      userMsg('first prompt', 'mid-1', 't1'),
      asstMsg('a reply', 't2'),
      userMsg('second prompt', 'mid-3', 't3'),
    ]
    const out = outlineEntries(msgs)
    expect(out.map(e => e.preview)).toEqual(['first prompt', 'second prompt'])
    expect(out.map(e => e.mid)).toEqual(['mid-1', 'mid-3'])
    expect(out.map(e => e.ts)).toEqual(['t1', 't3'])
  })
  it('drops a user turn that has neither mid nor ts (nothing to jump to)', () => {
    const out = outlineEntries([userMsg('unresolvable', undefined, undefined), userMsg('ok', 'mid-x', 'tx')])
    expect(out.map(e => e.preview)).toEqual(['ok'])
  })
  it('keeps a legacy turn that has a ts but no mid', () => {
    const out = outlineEntries([userMsg('legacy', undefined, 'tl')])
    expect(out).toEqual([{ mid: undefined, ts: 'tl', preview: 'legacy' }])
  })
})

describe('ChatOutlinePanel', () => {
  it('shows an empty state when there are no turns', () => {
    render(<ChatOutlinePanel entries={[]} onJumpToMessage={vi.fn()} />)
    expect(screen.getByTestId('chat-outline-empty-state')).toBeInTheDocument()
    expect(screen.queryByTestId('chat-outline-entry')).not.toBeInTheDocument()
  })

  it('renders one button per turn and jumps with (ts, mid) on click', () => {
    const onJump = vi.fn()
    render(
      <ChatOutlinePanel
        entries={[{ mid: 'mid-1', ts: 't1', preview: 'alpha' }, { mid: 'mid-2', ts: 't2', preview: 'beta' }]}
        onJumpToMessage={onJump}
      />,
    )
    const rows = screen.getAllByTestId('chat-outline-entry')
    expect(rows).toHaveLength(2)
    // Real buttons, keyboard-reachable by construction.
    expect(rows[0].tagName).toBe('BUTTON')
    fireEvent.click(rows[1])
    expect(onJump).toHaveBeenCalledWith('t2', 'mid-2')
  })

  it('activates on Space and marks the activated row aria-current', () => {
    const onJump = vi.fn()
    render(
      <ChatOutlinePanel
        entries={[{ mid: 'mid-1', ts: 't1', preview: 'alpha' }, { mid: 'mid-2', ts: 't2', preview: 'beta' }]}
        onJumpToMessage={onJump}
      />,
    )
    const rows = screen.getAllByTestId('chat-outline-entry')
    // No row is current before any activation.
    expect(rows.some(r => r.getAttribute('aria-current') === 'true')).toBe(false)
    fireEvent.keyDown(rows[0], { key: ' ' })
    expect(onJump).toHaveBeenCalledWith('t1', 'mid-1')
    // The activated row, and ONLY it, is now current.
    const after = screen.getAllByTestId('chat-outline-entry')
    expect(after[0].getAttribute('aria-current')).toBe('true')
    expect(after[1].getAttribute('aria-current')).toBeNull()
  })

  it('passes an empty ts (not undefined) when a turn has only a mid', () => {
    const onJump = vi.fn()
    render(<ChatOutlinePanel entries={[{ mid: 'mid-only', ts: undefined, preview: 'x' }]} onJumpToMessage={onJump} />)
    fireEvent.click(screen.getByTestId('chat-outline-entry'))
    expect(onJump).toHaveBeenCalledWith('', 'mid-only')
  })
})
