/**
 * Isolated capture entry for the chat Outline tab (ChatOutlinePanel).
 *
 * Mounts the REAL ChatOutlinePanel against the real stylesheet, theme tokens
 * and live i18n catalog. The panel derives its rows from a plain `entries`
 * prop, so no store, router or API is needed — the entries below stand in for
 * the user turns a session's transcript would project.
 *
 * Scenes via query string: ?theme=dark|light. The panel tracks its own
 * "current" entry on activation, so the capture script clicks a row to show
 * the aria-current state.
 */
import { createRoot } from 'react-dom/client'

import { ChatOutlinePanel } from '../src/pages/chat/ChatOutlinePanel'
import type { OutlineEntry } from '../src/pages/chat/ChatOutlinePanel'
import { initI18n } from '../src/i18n/all'
import '../src/index.css'

const params = new URLSearchParams(location.search)
const theme = params.get('theme') || 'dark'
document.documentElement.setAttribute('data-theme', theme === 'light' ? 'kiro-light' : 'kiro-dark')

const entries: OutlineEntry[] = [
  { mid: 'm1', ts: 't1', preview: 'Fix the login redirect bug' },
  { mid: 'm2', ts: 't2', preview: 'Add pagination to the users endpoint' },
  { mid: 'm3', ts: 't3', preview: 'Why is the build failing on Windows?' },
  { mid: 'm4', ts: 't4', preview: 'Refactor the auth middleware' },
  { mid: 'm5', ts: 't5', preview: 'Write tests for the outline projection' },
  { mid: 'm6', ts: 't6', preview: 'Update the README with local setup steps' },
  { mid: 'm7', ts: 't7', preview: 'Investigate the flaky integration test' },
]

initI18n('en')

const root = document.getElementById('root')!
// A side-panel-width shell so the tab reads as it does in the real panel.
root.style.width = '360px'
root.style.height = '640px'
root.className = 'bg-bg'
createRoot(root).render(<ChatOutlinePanel entries={entries} onJumpToMessage={() => {}} />)
