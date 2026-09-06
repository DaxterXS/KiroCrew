/**
 * Make every byte of a path VISIBLE in a consent label (GitHub #938).
 *
 * A filename may legally contain a tab, a newline, a zero-width space, or a
 * bidi override. Rendered raw, those either vanish or REORDER the glyphs on
 * screen, so two roots that differ only by such a code point would show one
 * identical label for two different grants -- or show a path that reads
 * left-to-right as somewhere else entirely. This is display-only: the value
 * echoed back to the backend as consent proof is always the raw root, never
 * this string.
 *
 * Deliberately NOT a truncation or elision helper -- the whole root stays in the
 * label, and every code point of it is either printed as-is or as an
 * unambiguous escape. The backslash is escaped too, so a literal `\x0A` in a
 * filename cannot impersonate a newline.
 *
 * Every string literal in this module is an escape-sequence fragment, never
 * copy, so the file is a named boundary in `eslint.i18n.config.js`.
 */

/** A code point the label must never print as-is.
 *
 *  The load-bearing member is `Default_Ignorable_Code_Point`: Unicode's OWN
 *  definition of "a conforming renderer shows nothing here". It is the
 *  invariant, not a list -- it covers the format category (`Cf`: zero-width
 *  joiners and spaces, bidi embeddings/overrides/isolates, U+FEFF, soft
 *  hyphen) AND the invisible code points that are NOT `Cf`: variation
 *  selectors U+FE00-FE0F and U+E0100-E01EF (`Mn`), the Hangul fillers U+115F,
 *  U+1160, U+3164, U+FFA0 (`Lo`), and the reserved default-ignorable ranges.
 *  Enumerating categories missed U+FE0F; naming the property cannot.
 *
 *  The rest is what a font cannot be trusted to render consistently: C0/C1
 *  controls (`Cc`), unassigned (`Cn`), private-use (`Co`), lone surrogates
 *  (`Cs`), and the line/paragraph separators (`Zl`/`Zp`) that would break the
 *  label onto a new line. Ordinary combining marks are deliberately NOT here:
 *  escaping them would mangle every Devanagari, Thai or Arabic path. */
const HIDDEN_RE = /[\p{Default_Ignorable_Code_Point}\p{Cc}\p{Cf}\p{Cn}\p{Co}\p{Cs}\p{Zl}\p{Zp}]/u

function escapeCodePoint(code: number): string {
  // Two-digit form for the C0/C1 range, brace form above it -- both are the
  // JavaScript escape spellings a developer already reads.
  return code < 0x100
    ? '\\x' + code.toString(16).padStart(2, '0')
    : '\\u{' + code.toString(16) + '}'
}

export function visiblePathLabel(root: string): string {
  let out = ''
  for (const ch of root) {
    if (ch === '\\') out += '\\\\'
    else if (HIDDEN_RE.test(ch)) out += escapeCodePoint(ch.codePointAt(0) ?? 0)
    else out += ch
  }
  return out
}
