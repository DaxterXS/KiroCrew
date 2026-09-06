/**
 * Screenshots for the chat Outline tab (ChatOutlinePanel).
 *
 * Drives the isolated capture entry (website/capture/chat-outline.html), which
 * mounts the REAL ChatOutlinePanel with a fixed set of sample user turns. Each
 * frame asserts its state before writing, so a frame cannot document the wrong
 * state:
 *   01-populated-dark   the outline listing seven user turns, none active
 *   02-current-dark     after activating a row: that row carries aria-current
 *   03-populated-light  light-theme parity
 *
 * Usage:
 *   npx vite --host 127.0.0.1 --port 6842 --strictPort   # in another shell
 *   node scripts/capture-chat-outline.mjs http://127.0.0.1:6842 ../temp-screenshots/chat-outline
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const BASE = process.argv[2] || 'http://127.0.0.1:6842'
const OUT = process.argv[3] || '../temp-screenshots/chat-outline'
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
let failed = false

function check(name, ok, detail) {
  console.log(`${name}: ${ok ? 'OK' : 'MISMATCH'} ${detail ?? ''}`)
  if (!ok) failed = true
  return ok
}

async function newPage(theme) {
  const page = await browser.newPage({ viewport: { width: 360, height: 640 }, deviceScaleFactor: 2 })
  await page.goto(`${BASE}/capture/chat-outline.html?theme=${theme}`, { waitUntil: 'networkidle' })
  await page.getByTestId('chat-outline-panel').waitFor({ state: 'visible', timeout: 15_000 })
  return page
}

// 01 — populated, no active entry.
{
  const page = await newPage('dark')
  const rows = page.getByTestId('chat-outline-entry')
  check('01 row count', (await rows.count()) === 7, `rows=${await rows.count()}`)
  check('01 no current yet', (await page.locator('[data-testid="chat-outline-entry"][aria-current="true"]').count()) === 0)
  await page.mouse.move(5, 5)
  await page.waitForTimeout(150)
  await page.screenshot({ path: `${OUT}/01-populated-dark.png` })
  await page.close()
}

// 02 — after activating row 3, it carries aria-current.
{
  const page = await newPage('dark')
  await page.getByTestId('chat-outline-entry').nth(2).click()
  const current = page.locator('[data-testid="chat-outline-entry"][aria-current="true"]')
  check('02 exactly one current', (await current.count()) === 1, `current=${await current.count()}`)
  await page.mouse.move(5, 5)
  await page.waitForTimeout(150)
  await page.screenshot({ path: `${OUT}/02-current-dark.png` })
  await page.close()
}

// 03 — light-theme parity.
{
  const page = await newPage('light')
  check('03 row count', (await page.getByTestId('chat-outline-entry').count()) === 7)
  await page.mouse.move(5, 5)
  await page.waitForTimeout(150)
  await page.screenshot({ path: `${OUT}/03-populated-light.png` })
  await page.close()
}

await browser.close()
if (failed) { console.error('capture: one or more frames mismatched'); process.exit(1) }
console.log(`captured 3 frames to ${OUT}`)
