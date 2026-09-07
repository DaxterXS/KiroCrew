/**
 * Screenshots for the native project-folder picker (#7217).
 *
 * Drives website/capture/native-folder-picker.html. Mounts the REAL
 * ProjectPicker with a stubbed availability endpoint. Scenes:
 *   - available:   folder_picker true, the native-picker button renders on the
 *                  Browse tab (aria-label "Open native folder dialog").
 *   - unavailable: folder_picker false, the button is absent.
 *
 * Each scene ASSERTS the rendered state before writing the file, so a frame
 * cannot silently photograph the wrong state.
 *
 * Usage:
 *   npx vite --host 127.0.0.1 --port 6841 --strictPort   # in another shell
 *   node scripts/capture-native-folder-picker.mjs http://127.0.0.1:6841 ../temp-screenshots/7217-native-folder-picker
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const BASE = process.argv[2] || 'http://127.0.0.1:6841'
const OUT = process.argv[3] || '../temp-screenshots/7217-native-folder-picker'
mkdirSync(OUT, { recursive: true })

const BTN_LABEL = 'Choose folder'
const browser = await chromium.launch({ args: ['--no-sandbox'] })
const page = await browser.newPage({ viewport: { width: 480, height: 520 }, deviceScaleFactor: 2 })
let failed = false

async function scene(name, theme, expectButton) {
  await page.goto(`${BASE}/capture/native-folder-picker.html?scene=${name}&theme=${theme}`)
  try {
    // Wait for the Browse-tab path field so the popover has mounted.
    await page.getByPlaceholder('/path/to/project').waitFor({ timeout: 10000 })
    const btn = page.getByRole('button', { name: new RegExp(BTN_LABEL) })
    if (expectButton) {
      await btn.waitFor({ timeout: 5000 })
      console.log(`${name} (${theme}): native picker button present OK`)
    } else {
      const count = await btn.count()
      if (count !== 0) throw new Error(`expected no native picker button, found ${count}`)
      console.log(`${name} (${theme}): native picker button absent OK`)
    }
    // Let the popover's slide-up/opacity animation settle so the frame is not
    // captured mid-fade (which reads as a dimmed/frozen dialog).
    await page.waitForTimeout(500)
    await page.screenshot({ path: `${OUT}/${name}-${theme}.png` })
  } catch (err) {
    console.error(`${name} (${theme}): ${err.message}`)
    failed = true
  }
}

await scene('available', 'kiro-dark', true)
await scene('available', 'kiro-light', true)
await scene('unavailable', 'kiro-dark', false)

await browser.close()
if (failed) {
  console.error('one or more scenes did not render the expected state — no misleading frame written')
  process.exit(1)
}
console.log(`wrote screenshots to ${OUT}`)
