/**
 * The path-scoped write tiers (GitHub #938).
 *
 * Two properties are pinned, and both are about SCOPE rather than looks:
 *
 *  1. The `pattern` a tier emits is the server's root, passed through
 *     BYTE-IDENTICAL. It is the consent proof the backend compares against its
 *     own stored root, so a client that trimmed, normalized or re-derived it
 *     would have its grant refused — or, worse, would be proposing a scope
 *     instead of confirming one.
 *  2. A tier the gateway WITHHELD does not render. An absent root means the
 *     server decided that scope cannot be described honestly (the file sits in
 *     a filesystem root, or the session's project does not contain it), and the
 *     menu must not fall back to a wider one.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'

vi.mock("@radix-ui/react-dropdown-menu", async () => await import("./__mocks__/@radix-ui/react-dropdown-menu"))

import { render, screen, fireEvent } from '@testing-library/react'
import TrustDropdown from '../components/TrustDropdown'
import { i18next } from '../i18n/all'

const btnClass = 'px-2 py-1 rounded text-sm'

const FILE = '/home/dev/project/src/api.ts'
const DIR = '/home/dev/project/src'
const WS = '/home/dev/project'

afterEach(async () => {
  await i18next.changeLanguage('en')
})

/** A write card: no command scopes, three path roots, no broad tier. */
function renderWriteCard(overrides: Record<string, unknown> = {}, onAction = () => {}) {
  return render(
    <TrustDropdown
      fullCommand=""
      baseCommand=""
      isShell={false}
      hasCommand={false}
      allowTrustAll={false}
      writeFileRoot={FILE}
      writeDirRoot={DIR}
      writeWorkspaceRoot={WS}
      className={btnClass}
      onAction={onAction}
      {...overrides}
    />,
  )
}

function open() {
  fireEvent.click(screen.getByText('Trust'))
  return screen.getAllByRole('menuitem')
}

describe('TrustDropdown write scopes', () => {
  it('offers exactly the three path tiers on a write card', () => {
    renderWriteCard()
    const texts = open().map(b => b.textContent)
    expect(texts).toHaveLength(3)
    expect(texts.some(t => t?.includes('writes to') && t?.includes(FILE))).toBe(true)
    expect(texts.some(t => t?.includes('writes in') && t?.includes(DIR))).toBe(true)
    expect(texts.some(t => t?.includes('anywhere under') && t?.includes(WS))).toBe(true)
  })

  it('orders the tiers narrowest first', () => {
    // A menu that listed the widest grant first would make the broad click the
    // easy one. Order is part of the safety of this control.
    renderWriteCard()
    const texts = open().map(b => b.textContent || '')
    expect(texts[0]).toContain('writes to')
    expect(texts[1]).toContain('writes in')
    expect(texts[2]).toContain('anywhere under')
  })

  it('emits the file root verbatim as the consent proof', () => {
    const onAction = vi.fn()
    renderWriteCard({}, onAction)
    fireEvent.click(open().find(b => b.textContent?.includes('writes to'))!)
    expect(onAction).toHaveBeenCalledWith('trust_path_file', FILE)
  })

  it('emits the directory root verbatim as the consent proof', () => {
    const onAction = vi.fn()
    renderWriteCard({}, onAction)
    fireEvent.click(open().find(b => b.textContent?.includes('writes in'))!)
    expect(onAction).toHaveBeenCalledWith('trust_path_dir', DIR)
  })

  it('emits the workspace root verbatim as the consent proof', () => {
    const onAction = vi.fn()
    renderWriteCard({}, onAction)
    fireEvent.click(open().find(b => b.textContent?.includes('anywhere under'))!)
    expect(onAction).toHaveBeenCalledWith('trust_path_ws', WS)
  })

  it('hides a tier whose root the gateway withheld', () => {
    // The server drops `write_ws_root` when the target is outside the project.
    renderWriteCard({ writeWorkspaceRoot: '' })
    const texts = open().map(b => b.textContent || '')
    expect(texts).toHaveLength(2)
    expect(texts.some(t => t.includes('anywhere under'))).toBe(false)
  })

  it('hides every path tier when the gateway offered no root', () => {
    // The presence of each root IS its offer; with none supplied, the family
    // renders nothing at all.
    renderWriteCard({ writeFileRoot: '', writeDirRoot: '', writeWorkspaceRoot: '' })
    fireEvent.click(screen.getByText('Trust'))
    expect(screen.queryAllByRole('menuitem')).toHaveLength(0)
  })

  it('withholds the broad tier the gateway did not prove', () => {
    // `trust` needs its own server proof (`trust_grantable`), which a write card
    // does not carry. Rendering it would offer a button the backend refuses.
    renderWriteCard()
    expect(screen.queryByText('Trust all tools')).not.toBeInTheDocument()
  })

  it('keeps the broad tier when the card does prove it', () => {
    renderWriteCard({ allowTrustAll: true })
    open()
    expect(screen.getByText('Trust all tools')).toBeInTheDocument()
  })

  it('shows command and path tiers together when both are grantable', () => {
    // Nothing about the path tiers is exclusive with the command ones; a future
    // tool carrying both must offer both rather than silently dropping one.
    render(
      <TrustDropdown
        fullCommand="fs_write api.ts"
        baseCommand=""
        isShell={false}
        hasCommand
        allowTrustAll
        writeDirRoot={DIR}
        className={btnClass}
        onAction={() => {}}
      />,
    )
    const texts = open().map(b => b.textContent || '')
    expect(texts.some(t => t.includes('fs_write api.ts'))).toBe(true)
    expect(texts.some(t => t.includes('writes in'))).toBe(true)
  })

  it('renders the COMPLETE root in the label, never elided', () => {
    // The user is agreeing to a LOCATION. A label that elided any part of it
    // could render two long roots differing only in the elided span as one
    // string, so the whole root must be in the visible text -- not only in the
    // hover tooltip, which touch never shows.
    const long = '/home/dev/' + 'nested/'.repeat(40) + 'file.ts'
    renderWriteCard({ writeFileRoot: long, writeDirRoot: '', writeWorkspaceRoot: '' })
    const item = open()[0]
    expect(item.textContent).toContain(long)
    expect(item.textContent).not.toContain('…')
    expect(item.querySelector('[title]')?.getAttribute('title')).toBe(long)
  })

  it('renders a control character in the root visibly, and still emits the raw root', () => {
    // A tab in a filename would collapse to a space in the label, so two roots
    // differing only by that byte would read as one. The LABEL escapes it; the
    // consent proof handed to onAction stays byte-identical to the root.
    const onAction = vi.fn()
    const tabbed = '/home/dev/proj\tect/f.ts'
    renderWriteCard({ writeFileRoot: tabbed, writeDirRoot: '', writeWorkspaceRoot: '' }, onAction)
    const item = open()[0]
    expect(item.textContent).toContain('proj\\x09ect')
    fireEvent.click(item)
    expect(onAction).toHaveBeenCalledWith('trust_path_file', tabbed)
  })

  it('word-wraps the sentence but lets only the path break anywhere', () => {
    // UX: `break-all` on the whole label split "workspace" mid-word at 320px.
    // The path span may break anywhere; the surrounding words may not.
    renderWriteCard()
    const item = open()[0]
    const label = item.querySelector('[title]')!
    expect(label.className).not.toContain('break-all')
    expect(label.querySelector('.font-mono')?.className).toContain('break-all')
  })

  it('keeps two long roots that differ only mid-path distinguishable', () => {
    // The exact collision class a label transform would create.
    const base = '/home/dev/' + 'nested/'.repeat(40)
    const a = base + 'alpha/' + 'deep/'.repeat(20) + 'f.ts'
    const b = base + 'bravo/' + 'deep/'.repeat(20) + 'f.ts'
    const { unmount } = renderWriteCard({ writeFileRoot: a, writeDirRoot: '', writeWorkspaceRoot: '' })
    const labelA = open()[0].textContent
    unmount()
    renderWriteCard({ writeFileRoot: b, writeDirRoot: '', writeWorkspaceRoot: '' })
    const labelB = open()[0].textContent
    expect(labelA).not.toBe(labelB)
  })

  it('folds the reject tiers in and relabels the trigger when asked', () => {
    // includeReject is the write-only card's shape: one trigger, five items,
    // and the trigger must not say "Trust" over a menu that can also reject.
    const seen: string[] = []
    renderWriteCard({ includeReject: true }, (a: string) => { seen.push(a) })
    expect(screen.queryByText('Trust')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Options'))
    const items = screen.getAllByRole('menuitem')
    expect(items).toHaveLength(5)
    // Reject tiers come LAST, in RejectDropdown's own order and decisions.
    // Selecting an item closes the menu, so re-open before the second click.
    fireEvent.click(items[3])
    fireEvent.click(screen.getByText('Options'))
    fireEvent.click(screen.getAllByRole('menuitem')[4])
    expect(seen).toEqual(['rejected_once', 'rejected'])
  })

  it('keeps the reject tiers out of the menu by default', () => {
    renderWriteCard()
    const items = open()
    expect(items.some(i => (i.textContent || '').includes('Reject'))).toBe(false)
  })

  it('renders translated tier labels', async () => {
    // The trigger is translated too, so this cannot reuse `open()`.
    await i18next.changeLanguage('ja')
    renderWriteCard()
    fireEvent.click(screen.getByText('信頼'))
    const texts = screen.getAllByRole('menuitem').map(b => b.textContent || '')
    expect(texts).toHaveLength(3)
    expect(texts.every(t => t.includes('書き込み'))).toBe(true)
  })
})
