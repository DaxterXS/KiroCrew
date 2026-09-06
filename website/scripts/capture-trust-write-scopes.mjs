/**
 * Screenshots of the path-scoped write tiers (GitHub #938).
 *
 * Drives the isolated capture entry (website/capture/trust-write-scopes.html),
 * which mounts the REAL TrustDropdown against the real stylesheet, theme tokens
 * and live i18n catalog. Radix renders the open menu into a portal outside the
 * capture root, so each frame is a viewport shot rather than an element shot.
 *
 * Every scene ASSERTS what it rendered before writing a file, so a frame can
 * never quietly show the wrong thing:
 *
 *   before        no trust control at all — the state the issue reports
 *   after         exactly three path tiers, narrowest first, each naming a root
 *   no-workspace  the withheld workspace tier is absent, not widened
 *   shell         a command card still renders its three command tiers
 *   row           the write card's action row, menu CLOSED: exactly two
 *                 controls (Allow once + the trigger), no standalone Reject
 *
 * The `after` scene additionally asserts its labels are UNCLIPPED and that the
 * menu fits the viewport: `innerText` returns a full label even when CSS has
 * ellipsised it, so a text check alone cannot see that the path a person is
 * agreeing to was cut off on screen. jsdom computes no layout, so that check
 * exists only here.
 *
 * Usage:
 *   node scripts/capture-trust-write-scopes.mjs                 # self-hosts Vite
 *   node scripts/capture-trust-write-scopes.mjs http://127.0.0.1:6823 <outDir>
 *
 * With no base URL it starts the dev server itself through Vite's JS API, on
 * loopback only, and closes it when the run ends -- so the whole capture is one
 * command with nothing left listening afterwards.
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const ARG_BASE = process.argv[2] && process.argv[2].startsWith('http') ? process.argv[2] : ''
const OUT = (ARG_BASE ? process.argv[3] : process.argv[2])
  || '../temp-screenshots/trust-write-scopes'
mkdirSync(OUT, { recursive: true })

/** Own dev server when none was handed to us. Bound to loopback explicitly. */
let server = null
let BASE = ARG_BASE
if (!BASE) {
  const { createServer } = await import('vite')
  server = await createServer({
    server: { host: '127.0.0.1', port: 0, strictPort: false },
    logLevel: 'warn',
  })
  await server.listen()
  const { port } = server.httpServer.address()
  BASE = `http://127.0.0.1:${port}`
  console.log(`self-hosted dev server at ${BASE}`)
}

// A write-only card's menu also carries the two reject tiers (AUTOSDE's
// max-two-buttons-per-row: the standalone Reject collapsed in here), so the
// `after` scenes expect 3 path tiers + 2 reject tiers.
const SCENES = [
  { name: 'write-scopes-before-dark', scene: 'before', theme: 'dark', expect: 0 },
  { name: 'write-scopes-after-dark', scene: 'after', theme: 'dark', expect: 5, geometry: true },
  { name: 'write-scopes-after-light', scene: 'after', theme: 'light', expect: 5 },
  { name: 'write-scopes-no-workspace-dark', scene: 'no-workspace', theme: 'dark', expect: 4 },
  { name: 'write-scopes-shell-unchanged-dark', scene: 'shell', theme: 'dark', expect: 3 },
  { name: 'write-scopes-row-closed-dark', scene: 'row', theme: 'dark', expect: null },
  // Narrow viewport: a path is longer than a command, so the width cap matters
  // more here than anywhere else the menu appears.
  { name: 'write-scopes-after-narrow', scene: 'after', theme: 'dark', expect: 5, width: 320 },
]

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 760, height: 320 }, deviceScaleFactor: 2 })

let failed = false
for (const s of SCENES) {
  const width = s.width ?? 760
  await page.setViewportSize({ width, height: width === 320 ? 620 : 320 })
  await page.goto(`${BASE}/capture/trust-write-scopes.html?scene=${s.scene}&theme=${s.theme}`)
  await page.waitForSelector('[data-capture-root]')

  // The write-only trigger says "Options"; command-shaped cards say "Trust".
  if (s.scene === 'row') {
    // Menu stays CLOSED. The property is the row's control count.
    const buttons = await page.locator('[data-approval-row] button').allInnerTexts()
    const ok = buttons.length === 2 && /Allow once/.test(buttons[0]) && /Options/.test(buttons[1])
    console.log(`${s.name}: controls=${buttons.length} [${buttons.map(b => b.trim()).join(' | ')}] ${ok ? 'OK' : 'MISMATCH'}`)
    if (!ok) { failed = true; continue }
    await page.screenshot({ path: `${OUT}/${s.name}.png` })
    continue
  }
  const trigger = page.getByRole('button', { name: /Trust|Options/ })
  const hasTrigger = await trigger.count() > 0
  let items = []
  if (hasTrigger) {
    await trigger.click()
    // Do not WAIT for a menuitem that may legitimately not exist — read what is
    // there.
    await page.waitForTimeout(150)
    items = (await page.locator('[role="menuitem"]').allInnerTexts()).map(t => t.trim())
  }

  let ok = items.length === s.expect
  let why = `items=${items.length} expected=${s.expect}`
  if (s.scene === 'before') {
    // The pre-change card had NO trust control; a trigger here would be a
    // frame of something that never shipped.
    ok = ok && !hasTrigger
    why += ` trigger=${hasTrigger}`
  }

  if (ok && s.scene === 'after') {
    // Narrowest first: the widest grant must never be the easy click.
    const ordered = /writes to/.test(items[0]) && /writes in/.test(items[1])
      && /anywhere under/.test(items[2])
    // Each tier must NAME its root, or the reader cannot tell them apart.
    const named = items[0].includes('ChatInput.tsx')
      && items[1].includes('/components') && items[2].includes('kiro-crew')
    // Reject tiers come LAST: the narrow one first, then the batch-wide one.
    const rejects = /Reject once/.test(items[3]) && /Reject all/.test(items[4])
    ok = ordered && named && rejects
    why += ` ordered=${ordered} named=${named} rejectsLast=${rejects}`
  }
  if (ok && s.scene === 'no-workspace') {
    const noWide = !items.some(t => /anywhere under/.test(t))
    ok = noWide
    why += ` workspaceTierAbsent=${noWide}`
  }
  if (ok && s.geometry) {
    const clipped = await page.locator('[role="menuitem"]').first().evaluate(el => {
      const span = el.querySelector('span')
      if (!span) return { ok: false, why: 'no label span' }
      const over = span.scrollWidth - span.clientWidth
      return { ok: over <= 1, why: `scrollWidth-clientWidth=${over}` }
    })
    const box = await page.locator('[role="menu"]').first().boundingBox()
    const vw = await page.evaluate(() => document.documentElement.clientWidth)
    const fits = Math.round(box.x + box.width) <= vw && Math.round(box.x) >= 0
    ok = clipped.ok && fits
    why += ` unclipped=${clipped.ok} (${clipped.why}) fitsViewport=${fits}`
  }

  console.log(`${s.name}: ${why} ${ok ? 'OK' : 'MISMATCH'}`)
  if (!ok) { failed = true; continue }
  await page.screenshot({ path: `${OUT}/${s.name}.png` })
}

await browser.close()
if (server) await server.close()
if (failed) {
  console.error('one or more scenes did not render as expected — no misleading frame written')
  process.exit(1)
}
console.log(`wrote ${SCENES.length} screenshots to ${OUT}`)
