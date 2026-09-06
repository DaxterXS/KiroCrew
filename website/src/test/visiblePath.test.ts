/**
 * `visiblePathLabel` exists so two roots can never share one consent label.
 * The property is INJECTIVITY on the code points a screen would otherwise hide
 * or reorder.
 */
import { describe, it, expect } from 'vitest'

import { visiblePathLabel } from '../utils/visiblePath'

describe('visiblePathLabel', () => {
  it('leaves an ordinary path untouched', () => {
    expect(visiblePathLabel('/home/dev/project/src/api.ts')).toBe('/home/dev/project/src/api.ts')
  })

  it('keeps ordinary non-ASCII text as-is', () => {
    expect(visiblePathLabel('/home/dev/项目/🙂/f.ts')).toBe('/home/dev/项目/🙂/f.ts')
  })

  it('makes a tab and a newline visible', () => {
    expect(visiblePathLabel('/a\tb')).toBe('/a\\x09b')
    expect(visiblePathLabel('/a\nb')).toBe('/a\\x0ab')
  })

  it('makes other C0/C1 control characters visible', () => {
    expect(visiblePathLabel('/a\x01b')).toBe('/a\\x01b')
    expect(visiblePathLabel('/a\x7fb')).toBe('/a\\x7fb')
    expect(visiblePathLabel('/a\x85b')).toBe('/a\\x85b')
  })

  it('makes zero-width and bidi format characters visible', () => {
    // The spoof class: U+200B renders as nothing, U+202E reverses what follows,
    // U+2066 isolates, U+FEFF is an invisible BOM.
    expect(visiblePathLabel('/a\u200Bb')).toBe('/a\\u{200b}b')
    expect(visiblePathLabel('/etc\u202Ecte/')).toBe('/etc\\u{202e}cte/')
    expect(visiblePathLabel('/a\u2066b')).toBe('/a\\u{2066}b')
    expect(visiblePathLabel('/a\uFEFFb')).toBe('/a\\u{feff}b')
    // Soft hyphen is Cf but below 0x100, so it takes the two-digit form.
    expect(visiblePathLabel('/a\u00ADb')).toBe('/a\\xadb')
  })

  it('makes default-ignorable code points outside Cf visible', () => {
    // U+FE0F (emoji variation selector) is Mn, U+3164 (Hangul filler) is Lo,
    // U+2060 (word joiner) is Cf: all three render as nothing, and only the
    // Default_Ignorable_Code_Point property names all of them.
    expect(visiblePathLabel('/a\uFE0Fb')).toBe('/a\\u{fe0f}b')
    expect(visiblePathLabel('/a\u3164b')).toBe('/a\\u{3164}b')
    expect(visiblePathLabel('/a\u2060b')).toBe('/a\\u{2060}b')
    expect(visiblePathLabel('/a\u{E0100}b')).toBe('/a\\u{e0100}b')
    expect(visiblePathLabel('/ab')).not.toBe(visiblePathLabel('/a\uFE0Fb'))
  })

  it('keeps ordinary combining marks, which scripts need to render', () => {
    // Devanagari vowel sign, Thai tone mark, Arabic fatha: visible glyph
    // components, not spoof vectors. Escaping them would mangle real paths.
    expect(visiblePathLabel('/\u0915\u093E')).toBe('/\u0915\u093E')
    expect(visiblePathLabel('/\u0E01\u0E48')).toBe('/\u0E01\u0E48')
    expect(visiblePathLabel('/\u0628\u064E')).toBe('/\u0628\u064E')
  })

  it('makes line and paragraph separators visible', () => {
    expect(visiblePathLabel('/a\u2028b')).toBe('/a\\u{2028}b')
  })

  it('makes private-use and lone surrogates visible', () => {
    expect(visiblePathLabel('/a\uE000b')).toBe('/a\\u{e000}b')
    expect(visiblePathLabel('/a\uD800b')).toBe('/a\\u{d800}b')
  })

  it('two roots differing only by a hidden code point render differently', () => {
    expect(visiblePathLabel('/a\tb')).not.toBe(visiblePathLabel('/a b'))
    expect(visiblePathLabel('/ab')).not.toBe(visiblePathLabel('/a\u200Bb'))
    expect(visiblePathLabel('/ab')).not.toBe(visiblePathLabel('/a\u202Eb'))
  })

  it('a literal backslash escape cannot impersonate the character it spells', () => {
    // Without escaping the backslash itself, "/a\\x09b" (literal chars) and
    // "/a<TAB>b" would both render as "/a\x09b" -- the collision just moved.
    expect(visiblePathLabel('/a\\x09b')).toBe('/a\\\\x09b')
    expect(visiblePathLabel('/a\\x09b')).not.toBe(visiblePathLabel('/a\tb'))
  })
})
