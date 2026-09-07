/**
 * Evidence for the native project-folder picker (#7217).
 *
 * THE CHANGE: the project picker's Browse tab gains a native-folder-dialog
 * button next to Select, shown ONLY where the gateway can open a host chooser
 * (local macOS/Windows). This mounts the REAL ProjectPicker component with the
 * REAL i18n keys; the availability config and directory listing are served by a
 * stubbed fetch so the frame photographs the shipped markup and strings without
 * a running gateway.
 *
 * Scenes, selected with ?scene=:
 *   ?scene=available   — folder_picker: true, so the native picker button
 *     (aria-label "Open native folder dialog") renders on the Browse tab.
 *   ?scene=unavailable — folder_picker: false (a remote gateway / plain
 *     browser), so the button is absent and the typed-path field stands alone.
 */
import { useRef } from 'react'
import { createRoot } from 'react-dom/client'

import ProjectPicker from '../src/components/ProjectPicker'
import { initI18n } from '../src/i18n'
import { applyFallbackTheme } from '../src/apps/mochi/src/shared/themes'
import '../src/index.css'

const params = new URLSearchParams(location.search)
const scene = params.get('scene') ?? 'available'
const theme = params.get('theme') ?? 'kiro-dark'
const available = scene !== 'unavailable'

document.documentElement.setAttribute('data-theme', theme)
applyFallbackTheme()
initI18n('en')

// Stub the two endpoints the picker calls on open so the frame is deterministic
// and needs no gateway. Everything else falls through to the real fetch.
const realFetch = window.fetch.bind(window)
window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === 'string' ? input : input.toString()
  if (url.includes('/api/project-picker/config')) {
    return Promise.resolve(new Response(JSON.stringify({ folder_picker: available }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }))
  }
  if (url.includes('/api/recent-projects')) {
    return Promise.resolve(new Response(JSON.stringify({ dirs: [] }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }))
  }
  if (url.includes('/api/browse-dirs')) {
    return Promise.resolve(new Response(JSON.stringify({
      path: '/home/you/projects',
      parent: '/home/you',
      dirs: [
        { name: 'acme-storefront', path: '/home/you/projects/acme-storefront' },
        { name: 'design-tokens', path: '/home/you/projects/design-tokens' },
        { name: 'legacy-admin', path: '/home/you/projects/legacy-admin' },
      ],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
  }
  return realFetch(input, init)
}) as typeof window.fetch

function Scene() {
  const anchorRef = useRef<HTMLButtonElement>(null)
  return (
    <div data-capture-root style={{ width: 480, height: 520, background: 'var(--bg)', color: 'var(--text)', padding: 24 }}>
      <button
        ref={anchorRef}
        style={{ padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-elevated)', color: 'var(--text)' }}
      >
        Select Project
      </button>
      <ProjectPicker
        open
        onOpenChange={() => {}}
        anchorRef={anchorRef}
        onSelect={() => {}}
      />
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<Scene />)
