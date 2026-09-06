/**
 * Evidence for the path-scoped write tiers (GitHub #938).
 *
 * THE PROBLEM: for a file-write tool the trust menu was gated on a COMMAND
 * scope, which a write tool does not have. The menu therefore never appeared,
 * and the only choices were "allow once" and the broadest "trust all tools" —
 * nothing in between for the file, its directory, or the workspace.
 *
 * The scene mounts the REAL TrustDropdown against the real stylesheet, theme
 * tokens and live i18n catalog, driven by the same props ChatInput passes it
 * from a pending write card. Nothing here re-implements the component, its
 * classes, or its strings; the roots are the values the gateway derives
 * server-side, which the client only ever echoes back.
 *
 * The line above the control is harness chrome, labelled as such, so a frame
 * shows which write request produced the tiers.
 *
 *   ?scene=before|after|no-workspace|shell|row   ?theme=dark|light
 *
 * `row` shows the write card's whole action row with the menu CLOSED --
 * Allow once beside the one trigger, no standalone Reject -- which is the
 * two-control shape the AUTOSDE row cap requires and the other scenes
 * crop out.
 */
import { createRoot } from 'react-dom/client'
import { CheckCircle } from 'lucide-react'

import TrustDropdown from '../src/components/TrustDropdown'
import { initI18n } from '../src/i18n'
import '../src/index.css'

const FILE = '/home/dev/kiro-crew/website/src/components/ChatInput.tsx'
const DIR = '/home/dev/kiro-crew/website/src/components'
const WS = '/home/dev/kiro-crew'

const params = new URLSearchParams(location.search)
const scene = params.get('scene') ?? 'after'
const theme = params.get('theme') === 'light' ? 'light' : 'dark'

document.documentElement.setAttribute('data-theme', theme === 'light' ? 'kiro-light' : 'kiro-dark')

initI18n('en')

/** The classes ChatInput gives the control it renders, so the trigger is the
 *  size and weight it has in the chat approval row. */
const BTN = 'px-2.5 py-1 rounded-md border border-border bg-transparent text-muted ' +
  'text-[13px] cursor-pointer font-body inline-flex items-center gap-1'

/** Scenes, each spelled as the props ChatInput derives for that pending card.
 *  `before` is the pre-fix state: a write card proved no command scope, so the
 *  menu had nothing to show. */
const SCENES: Record<string, Record<string, unknown>> = {
  before: {
    fullCommand: '', baseCommand: '', isShell: false, hasCommand: false,
    allowTrustAll: false, writeFileRoot: '', writeDirRoot: '', writeWorkspaceRoot: '',
  },
  after: {
    fullCommand: '', baseCommand: '', isShell: false, hasCommand: false,
    allowTrustAll: false, includeReject: true,
    writeFileRoot: FILE, writeDirRoot: DIR, writeWorkspaceRoot: WS,
  },
  // Target outside the session's project: the gateway withholds the workspace
  // root, and the menu must not invent one.
  'no-workspace': {
    fullCommand: '', baseCommand: '', isShell: false, hasCommand: false,
    allowTrustAll: false,
    includeReject: true,
    writeFileRoot: '/tmp/scratch/notes.md',
    writeDirRoot: '/tmp/scratch',
    writeWorkspaceRoot: '',
  },
  // Regression guard: a shell card still renders exactly its three command
  // tiers, unchanged by this feature.
  shell: {
    fullCommand: 'npm run build', baseCommand: 'npm', isShell: true, hasCommand: true,
    allowTrustAll: true,
    writeFileRoot: '', writeDirRoot: '', writeWorkspaceRoot: '',
  },
}

const props = SCENES[scene === 'row' ? 'after' : scene] ?? SCENES.after

/** ChatInput's own approval-row button classes, so the closed row is the
 *  size, weight and tint it has in the composer. */
const ROW_BTN = 'inline-flex items-center gap-1 px-2 py-1 rounded-md '
  + 'bg-[color-mix(in_srgb,var(--warn)_12%,transparent)] border border-border text-text '
  + 'text-[12px] cursor-pointer font-body'
const asked = scene === 'shell'
  ? 'run: npm run build'
  : `write to: ${(props.writeFileRoot as string) || FILE}`

createRoot(document.getElementById('root')!).render(
  <div data-capture-root className="bg-bg text-text p-5 w-[720px] flex flex-col gap-3">
    {/* Harness chrome: names the request whose tiers are under test. */}
    <div className="text-[11px] text-muted font-mono break-all">
      <span className="not-italic text-subtle">the agent wants to </span>{asked}
    </div>
    <div>
      {/* `before` is the pre-change write card: ChatInput gated the whole
          control on a command scope, so no Trust control rendered at all.
          Mounting the dropdown here would show a trigger that did not exist. */}
      {scene === 'row' ? (
        <div data-approval-row className="flex gap-1.5 flex-wrap items-center">
          <button className={ROW_BTN}><CheckCircle size={12} className="shrink-0" />Allow once</button>
          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any -- scene table is deliberately prop-shaped */}
          <TrustDropdown {...(props as any)} className={ROW_BTN} onAction={() => {}} />
        </div>
      ) : scene === 'before' ? (
        <span className="text-[11px] text-muted italic">(no trust control rendered for a write card)</span>
      ) : (
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- scene table is deliberately prop-shaped
        <TrustDropdown {...(props as any)} className={BTN} onAction={() => {}} />
      )}
    </div>
  </div>,
)
