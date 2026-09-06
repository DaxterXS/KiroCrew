import { useState } from 'react'
import { Ban, Handshake, MoreHorizontal, Shield, ShieldPlus, ShieldCheck, ChevronDown, FileText, FolderOpen, FolderTree, XCircle } from 'lucide-react'
import { Trans } from 'react-i18next'
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator
} from './ui/dropdown-menu'
import { baseCommandLabel, trustBasePattern, truncateCommandLabel } from '../utils/trustPatterns'
import { visiblePathLabel } from '../utils/visiblePath'

import { i18nT } from '../i18n/t'
interface TrustDropdownProps {
  fullCommand: string
  baseCommand: string
  isShell: boolean
  /** Whether the approval carries an actual tool command. Agent-role channel
      approvals pass false because command-scoped tiers would describe the
      wrong thing and emit decisions (`trust_command` / `trust_base`) the
      channel backend refuses; shell-command channel approvals pass true.
      Explicit rather than inferred from `fullCommand`, so command-bearing
      surfaces keep every tier no matter what the command text looks like. */
  hasCommand?: boolean
  /** Whether the broadest "trust all tools" tier may be offered. False for a
      card whose only grantable scopes are the path tiers below: the gateway sets
      `trust_grantable` alongside the command scopes, so offering the broad tier
      on a write card would render a button the backend refuses. */
  allowTrustAll?: boolean
  /** Server-derived roots, one per path tier -- the fs-write scopes from
      GitHub #938. Each is echoed back verbatim as the consent proof for its
      grant, so they are passed through untouched -- NEVER re-derived here. A
      frontend that computed a directory from the file root itself would be
      inventing authority the backend then has to trust. An absent root means
      the gateway withheld that tier (the file sits in a filesystem root, or
      the session has no project directory containing it), and it must stay
      hidden rather than fall back to a wider one. */
  writeFileRoot?: string
  writeDirRoot?: string
  writeWorkspaceRoot?: string
  /** Fold the two reject tiers into THIS menu, after a separator, and label
      the trigger "Options" instead of "Trust". AUTOSDE's
      `max-two-buttons-per-row` caps a horizontal action group at two controls
      and legacy-exempts rows that already carry three "but must not grow" -- a
      write-only card is a NEW row shape, so its third control (the standalone
      Reject) has to collapse in here. A trigger counts as one control however
      many items it holds; the trigger label changes with the contents so it
      never says "Trust" over a menu that can also reject. */
  includeReject?: boolean
  disabled?: boolean
  className?: string
  // Overrides the catalog key for the "trust all tools" option. The default
  // label reads as session-scoped; a surface whose `trust` decision grants
  // something wider (e.g. channel-wide and persisted to disk) must pass a key
  // that names the actual grant, so consent matches what is being consented to.
  trustAllLabelKey?: string
  onAction: (action: string, pattern?: string) => void
}

export default function TrustDropdown({ fullCommand, baseCommand, isShell, hasCommand = true, allowTrustAll = true, writeFileRoot = '', writeDirRoot = '', writeWorkspaceRoot = '', includeReject = false, disabled, className, trustAllLabelKey, onAction }: TrustDropdownProps) {
  const [open, setOpen] = useState(false)

  // Pattern shaping lives in utils/trustPatterns so every surface that offers
  // tiered trust grants an identical scope for the same click.
  const truncated = truncateCommandLabel(fullCommand)
  const basePattern = trustBasePattern(baseCommand)
  const baseLabel = baseCommandLabel(baseCommand)

  // Path tiers, narrowest first. Each is shown only when the gateway supplied
  // its root: the presence of the root IS the offer, so a withheld tier cannot
  // be resurrected here.
  const showWriteFile = !!writeFileRoot
  const showWriteDir = !!writeDirRoot
  const showWriteWorkspace = !!writeWorkspaceRoot

  // The command label is interpolated INTO a whole sentence rather than glued
  // between two fragments: word order around a quoted operand differs per
  // language, and a fragment pair can only express the English one.
  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button disabled={disabled} className={className}>
          {includeReject
            ? <><MoreHorizontal size={12} className="shrink-0" />{i18nT('components.trustDropdown.options')}</>
            : <><Handshake size={12} className="shrink-0" />{i18nT('components.trustDropdown.trust')}</>}
          <ChevronDown size={10} className="shrink-0 opacity-70" />
        </button>
      </DropdownMenuTrigger>
      {/* The width cap is viewport-aware: a flat max-w overflows a narrow screen
          (measured at 320px, the menu reached 440px and ran off the right edge),
          which hides the very label this menu exists to make readable. */}
      <DropdownMenuContent side="top" align="end" className="min-w-[220px] max-w-[min(450px,calc(100vw-2rem))]">
        {hasCommand && (
          <DropdownMenuItem
            className="gap-2 text-[12px]"
            onSelect={() => onAction('trust_command', fullCommand)}
          >
            <Shield size={12} className="shrink-0 text-accent" />
            {/* The untruncated command as a tooltip: this grant is an exact-string
                match, so the user must be able to read the whole thing before
                agreeing to it. No `truncate` here on purpose -- CSS ellipsis would
                clip the tail that `truncateCommandLabel` deliberately preserved,
                re-colliding two commands that differ only in their filename. The
                label wraps instead; the menu's own max-width still bounds it. */}
            <span className="min-w-0 break-all" title={fullCommand}>
              <Trans
                i18nKey="components.trustDropdown.trust_this_command"
                values={{ cmd: truncated }}
                components={{ mono: <span className="font-mono" /> }}
              />
            </span>
          </DropdownMenuItem>
        )}
        {hasCommand && isShell && (
          <DropdownMenuItem
            className="gap-2 text-[12px]"
            onSelect={() => onAction('trust_base', basePattern)}
          >
            <ShieldPlus size={12} className="shrink-0 text-ok" />
            <span className="truncate">
              <Trans
                i18nKey="components.trustDropdown.trust_all_base"
                values={{ base: baseLabel }}
                components={{ mono: <span className="font-mono" /> }}
              />
            </span>
          </DropdownMenuItem>
        )}
        {showWriteFile && (
          <DropdownMenuItem
            className="gap-2 text-[12px]"
            onSelect={() => onAction('trust_path_file', writeFileRoot)}
          >
            <FileText size={12} className="shrink-0 text-accent" />
            {/* The COMPLETE root, untransformed, and no `truncate`: the user is
                agreeing to a location, so every byte of it must be readable.
                No label-side elision either -- two long roots differing only in
                an elided middle would render one consent label for two grants.
                The label wraps inside the menu's viewport-aware width cap. */}
            <span className="min-w-0" title={writeFileRoot}>
              <Trans
                i18nKey="components.trustDropdown.trust_write_file"
                values={{ path: visiblePathLabel(writeFileRoot) }}
                components={{ mono: <span className="font-mono break-all" /> }}
              />
            </span>
          </DropdownMenuItem>
        )}
        {showWriteDir && (
          <DropdownMenuItem
            className="gap-2 text-[12px]"
            onSelect={() => onAction('trust_path_dir', writeDirRoot)}
          >
            <FolderOpen size={12} className="shrink-0 text-ok" />
            <span className="min-w-0" title={writeDirRoot}>
              <Trans
                i18nKey="components.trustDropdown.trust_write_dir"
                values={{ path: visiblePathLabel(writeDirRoot) }}
                components={{ mono: <span className="font-mono break-all" /> }}
              />
            </span>
          </DropdownMenuItem>
        )}
        {showWriteWorkspace && (
          <DropdownMenuItem
            className="gap-2 text-[12px]"
            onSelect={() => onAction('trust_path_ws', writeWorkspaceRoot)}
          >
            <FolderTree size={12} className="shrink-0 text-warn" />
            <span className="min-w-0" title={writeWorkspaceRoot}>
              <Trans
                i18nKey="components.trustDropdown.trust_write_workspace"
                values={{ path: visiblePathLabel(writeWorkspaceRoot) }}
                components={{ mono: <span className="font-mono break-all" /> }}
              />
            </span>
          </DropdownMenuItem>
        )}
        {allowTrustAll && (
        <DropdownMenuItem
          className="gap-2 text-[12px]"
          onSelect={() => onAction('trust')}
        >
          <ShieldCheck size={12} className="shrink-0 text-warn" />
          {/* min-w-0 lets a long scope-qualified label wrap inside the menu's
              viewport-aware width cap instead of overflowing it. */}
          <span className="min-w-0">{trustAllLabelKey ? i18nT(trustAllLabelKey) : i18nT('components.trustDropdown.trust_all_tools')}</span>
        </DropdownMenuItem>
        )}
        {includeReject && (
          <>
            <DropdownMenuSeparator />
            {/* Same two tiers, same order and same decisions as RejectDropdown:
                the narrower reject-once before the batch-wide reject, so the
                reader meets the option that stops one call first. */}
            <DropdownMenuItem
              className="gap-2 text-[12px]"
              onSelect={() => onAction('rejected_once')}
            >
              <XCircle size={12} className="shrink-0 text-warn" />
              <span className="min-w-0">{i18nT('components.rejectDropdown.reject_once')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              className="gap-2 text-[12px]"
              onSelect={() => onAction('rejected')}
            >
              <Ban size={12} className="shrink-0 text-danger" />
              <span className="min-w-0">{i18nT('components.rejectDropdown.reject_all')}</span>
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
