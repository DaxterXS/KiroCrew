/**
 * The composer's approval card for a file-WRITE tool (GitHub #938).
 *
 * Before this, a write card had no Trust menu at all: the menu was gated on
 * `trust_command_grantable`, which the gateway only sets for a card carrying a
 * command. A write tool carries a PATH, so the user's only choices were
 * allow-once and reject — the complaint in the issue.
 *
 * What is pinned here is the gate and the wire call, not the menu's internals
 * (those live in TrustDropdownWriteScopes.test.tsx): the menu OPENS for a card
 * with only path scopes, the broad "trust all tools" tier stays hidden because
 * the gateway proved no such grant for it, and a tier click reaches the backend
 * with the server's own root as its consent proof.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock("@radix-ui/react-dropdown-menu", async () => await import("./__mocks__/@radix-ui/react-dropdown-menu"))
vi.mock("@radix-ui/react-popover", async () => await import("./__mocks__/@radix-ui/react-popover"))

import { screen, fireEvent, waitFor } from '@testing-library/react'
import { renderWithProviders, createTestStore } from './helpers'
import ChatInput from '../components/ChatInput'
import { api } from '../api/client'
import type { RootState } from '../store'

vi.mock('../api/client', () => {
  class MockApiError extends Error {
    readonly status: number
    constructor(status: number, message: string) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  }
  return {
    api: {
      resolveApproval: vi.fn(() => Promise.resolve({})),
      approveChatSlot: vi.fn(() => Promise.resolve({})),
    },
    ApiError: MockApiError,
  }
})

const defaultProps = { value: '', onChange: vi.fn(), onSend: vi.fn() }

const FILE = '/home/dev/project/src/api.ts'
const DIR = '/home/dev/project/src'
const WS = '/home/dev/project'

/** A pending WRITE approval: a target path and roots, and no command scopes. */
function writeApprovalState(metaOverrides: Record<string, unknown> = {}): Partial<RootState> {
  return {
    chat: {
      activeSlot: 'slot-1',
      messages: [
        { role: 'user', content: 'edit the api' },
        {
          role: 'permission',
          content: 'Editing api.ts',
          meta: {
            approval_id: 'ap-w1',
            request_id: 'req-w1',
            tool_input: '{"path":"/home/dev/project/src/api.ts"}',
            tool_title: 'Editing api.ts',
            is_shell: '',
            tool_call_id: 'tc-w1',
            write_file_root: FILE,
            write_dir_root: DIR,
            write_ws_root: WS,
            ...metaOverrides,
          },
        },
      ],
      toolLog: [],
      slotStatusDetail: {},
    } as unknown as RootState['chat'],
    dashboard: {
      slots: [{ key: 'slot-1', messages: 2, running: true, pending_approval: true, waiting_for_input: false, last_activity_ts: undefined }],
      approvalMode: 'normal',
      connected: true,
      channelTrusted: false,
      refreshTrigger: 0,
      unreadSlots: [],
      updateProgress: null,
    } as unknown as RootState['dashboard'],
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ChatInput write-scope approval', () => {
  it('offers the scope menu for a write card that has no command scope', () => {
    // The write-only trigger says "Options", not "Trust": the same menu also
    // holds the two reject tiers (see the row-shape tests below), so a "Trust"
    // label would sit over actions that are not grants.
    const store = createTestStore(writeApprovalState())
    renderWithProviders(<ChatInput {...defaultProps} />, { store })
    fireEvent.click(screen.getByText('Options'))
    // Three path tiers plus the two reject tiers.
    expect(screen.getAllByRole('menuitem')).toHaveLength(5)
  })

  it('withholds the broad tier the gateway did not prove for this card', () => {
    const store = createTestStore(writeApprovalState())
    renderWithProviders(<ChatInput {...defaultProps} />, { store })
    fireEvent.click(screen.getByText('Options'))
    expect(screen.queryByText('Trust all tools')).not.toBeInTheDocument()
  })

  it('keeps the approval row at two action controls (AUTOSDE cap)', () => {
    // max-two-buttons-per-row legacy-exempts the pre-existing command row but a
    // write-only card is a NEW row shape and must comply: Allow once plus ONE
    // menu trigger. A standalone Reject trigger here would be a third sibling.
    const store = createTestStore(writeApprovalState())
    renderWithProviders(<ChatInput {...defaultProps} />, { store })
    const allow = screen.getByText('Allow once').closest('button')!
    const group = allow.parentElement!
    const controls = Array.from(group.children).filter(el => el.tagName === 'BUTTON')
    expect(controls).toHaveLength(2)
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument()
  })

  it('shows no scope menu on an unattended card', () => {
    // A cron/task-runner card can carry write roots, but session trust is
    // incoherent for a job that is not this session: handleApprovalAction
    // would silently downgrade the durable tier to a one-shot approval. The
    // menu is withheld, like every other Trust control, and the standalone
    // Reject returns so the row keeps its two controls.
    const store = createTestStore(writeApprovalState({ source: 'cron' }))
    renderWithProviders(<ChatInput {...defaultProps} />, { store })
    expect(screen.queryByText('Options')).not.toBeInTheDocument()
    expect(screen.queryByText('Trust')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
  })

  it('still rejects once from inside the scope menu', async () => {
    // Folding the reject tiers into the menu must not change their wire shape:
    // a one-shot rejection resolves the approval, it grants nothing.
    const store = createTestStore(writeApprovalState())
    renderWithProviders(<ChatInput {...defaultProps} />, { store })
    fireEvent.click(screen.getByText('Options'))
    fireEvent.click(screen.getByText(/Reject once/))
    await waitFor(() => expect(api.resolveApproval).toHaveBeenCalledWith('ap-w1', 'reject_once'))
    expect(api.approveChatSlot).not.toHaveBeenCalled()
  })

  it('sends the directory grant with the server root as its consent proof', async () => {
    const store = createTestStore(writeApprovalState())
    renderWithProviders(<ChatInput {...defaultProps} />, { store })
    fireEvent.click(screen.getByText('Options'))
    const item = screen.getAllByRole('menuitem').find(b => b.textContent?.includes('writes in'))!
    fireEvent.click(item)
    await waitFor(() =>
      expect(api.approveChatSlot).toHaveBeenCalledWith('slot-1', 'trust_path_dir', {
        request_id: 'ap-w1',
        pattern: DIR,
      }),
    )
  })

  it('sends the workspace grant with the project root', async () => {
    const store = createTestStore(writeApprovalState())
    renderWithProviders(<ChatInput {...defaultProps} />, { store })
    fireEvent.click(screen.getByText('Options'))
    const item = screen.getAllByRole('menuitem').find(b => b.textContent?.includes('anywhere under'))!
    fireEvent.click(item)
    await waitFor(() =>
      expect(api.approveChatSlot).toHaveBeenCalledWith('slot-1', 'trust_path_ws', {
        request_id: 'ap-w1',
        pattern: WS,
      }),
    )
  })

  it('shows no Trust menu when the card carries neither command nor path scope', () => {
    // The pre-#938 state for anything ungrantable, and still the correct one:
    // a card with no proven scope offers allow-once and reject only.
    const store = createTestStore(
      writeApprovalState({ write_file_root: '', write_dir_root: '', write_ws_root: '' }),
    )
    renderWithProviders(<ChatInput {...defaultProps} />, { store })
    expect(screen.queryByText('Trust')).not.toBeInTheDocument()
    expect(screen.queryByText('Options')).not.toBeInTheDocument()
  })

  it('shows only the tiers the gateway offered', async () => {
    // Target outside the project: the gateway withholds the workspace root, and
    // the card must not invent one.
    const store = createTestStore(writeApprovalState({ write_ws_root: '' }))
    renderWithProviders(<ChatInput {...defaultProps} />, { store })
    fireEvent.click(screen.getByText('Options'))
    const texts = screen.getAllByRole('menuitem').map(b => b.textContent || '')
    // Two offered path tiers plus the two reject tiers.
    expect(texts).toHaveLength(4)
    expect(texts.some(t => t.includes('anywhere under'))).toBe(false)
  })
})
