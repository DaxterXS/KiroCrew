"""Path-scoped trust grants for file-WRITE tools.

Command-shaped trust lives in :mod:`kiro_crew.trust_patterns`: a grant there is
an fnmatch pattern matched against a command string.  A write tool has no
command — it has a target PATH — and the two cannot share a store, for two
reasons that are properties of the existing matcher rather than opinions:

* ``trust_patterns._tool_matches`` compares with ``str.lower()``.  On a
  case-sensitive filesystem ``/srv/Secret`` and ``/srv/secret`` are different
  files, so folding a path through that matcher would let a grant for one
  authorize a write to the other.
* ``trust_patterns.split_command_segments`` SPLITS its input on ``|``, ``&``,
  ``;`` and newline before matching.  Those bytes are legal in a filename, so a
  path carrying one would be chopped into fragments and matched against
  unrelated patterns.

So grants here are not patterns at all.  A grant is
``(tool identity, real root, subtree?)`` and matching is an explicit
path-containment check on REALPATHS.  There is no wildcard language to reason
about, which is the point: the only way to widen one of these grants is to ask
for a wider root.

Scope vocabulary (GitHub #938) — narrowest first:

``file``
    This tool may write this one file, again, without asking.
``dir``
    …anything directly under the file's own directory, and below it.
``workspace``
    …anything under the session's project directory.

Persistence, review and revocation are deliberately absent: they are #1194.
A grant lives on the slot for the session's lifetime, exactly like
``_trusted_patterns``, and dies with it.

Everything here is SYNCHRONOUS and touches the filesystem (``os.path.realpath``
follows symlinks).  Callers on the event loop must run these through
``asyncio.to_thread``.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from typing import NamedTuple

from kiro_crew.platform.governance import BUILTIN_TOOL_SCOPES
from kiro_crew.platform.tool_paths import target_paths

#: The ACP ``toolCall.kind`` that denotes a file write/edit.  Same literal the
#: governance intersection plane keys ``filesystem.write`` on
#: (``platform.governance._KIND_EDIT``).  The kind is NECESSARY but never
#: SUFFICIENT: it is agent/backend-authored wire data, so it can only WITHHOLD a
#: tier (a backend that omits it gets no path tiers), never grant one — the
#: grant-carrying classification is :data:`_WRITE_ONLY_BUILTIN_TOOLS` below.
WRITE_TOOL_KIND = "edit"

#: The canonical built-in tool names whose ONLY governed capability is
#: ``filesystem.write`` — derived from the same table the governance ceiling
#: keys enforcement on, so a new write builtin is a data change in ONE place.
#: This set, checked against the provenance-verified ``_meta.kiro`` identity,
#: is what classifies a permission request as a file write.  The payload's
#: ``kind`` must never make that call: it is authored by the very backend the
#: module's threat model distrusts, so a forged ``kind: "edit"`` on a
#: destructive tool could otherwise mint — and later spend — a durable path
#: grant that bypasses approval on irreversible operations.
#:
#: ``==`` on the scope tuple, not ``in``: a tool that writes files AND holds any
#: other capability (``code`` shells out — ``commands`` scope) must not be
#: auto-approvable through a grant whose label says only "write to this path".
#: MCP tools never qualify — no provenance-verified signal says what an
#: arbitrary MCP tool does with a ``path`` argument, so they fail closed to the
#: interactive prompt.
_WRITE_ONLY_BUILTIN_TOOLS: frozenset[str] = frozenset(
    name for name, scopes in BUILTIN_TOOL_SCOPES.items() if scopes == ("filesystem.write",)
)


class WriteGrant(NamedTuple):
    """One stored path grant.

    ``tool_key`` is the encoded canonical tool identity from
    :func:`write_tool_trust_key`.  It is part of the grant, not decoration: a
    grant means "THIS tool may write here", so a grant earned by ``fs_write``
    can never authorize an MCP tool that merely also carries a ``path``
    argument.  Identity binding stops the CROSS-tool escape (spending someone
    else's grant); the SAME-tool escape — a destructive tool forging
    ``kind: "edit"`` to mint and later spend a grant of its own — is closed by
    :data:`_WRITE_ONLY_BUILTIN_TOOLS`, which classifies a write from the
    provenance-verified identity, never from the backend-authored ``kind``.

    ``root`` is an absolute realpath.  ``subtree`` False means the grant covers
    that exact path only (the ``file`` scope); True means it covers the root and
    everything below it (``dir`` and ``workspace``).
    """

    tool_key: str
    root: str
    subtree: bool


def _exact_identity_component(value: str) -> str:
    """Encode one identity component EXACTLY as given — no case folding.

    ``trust_patterns._trust_identity_component`` lowercases first, because the
    command matcher it feeds has always compared with ``str.lower()``.  A path
    grant has no such history, and folding here would merge two case-distinct
    MCP tool identities onto ONE grant key — a grant earned by ``srv:tool``
    would silently authorize ``srv:Tool``, a tool the user never approved.
    Hex keeps the key free of delimiters, so the ``:``-joined pair stays
    injective.
    """
    return value.encode("utf-8", "surrogatepass").hex()


def write_tool_trust_key(mcp_server_name: str, tool_name: str) -> str:
    """Return an injective durable key for the tool a path grant belongs to.

    Both components are hex-encoded exactly as given (see
    :func:`_exact_identity_component`), so ``("a", "b__c")`` cannot collide
    with ``("a__b", "c")`` — the collision class that made the plain
    ``mcp__server__tool`` spelling unusable as authority — and two
    case-distinct tools never share a key.

    ``tool_name`` is required; ``mcp_server_name`` is legitimately empty for a
    built-in tool (``fs_write``), which is the common case here.
    """
    if not tool_name:
        return ""
    return (
        "fswrite-trust:v2:"
        f"{_exact_identity_component(mcp_server_name)}:{_exact_identity_component(tool_name)}"
    )


def _is_filesystem_root(path: str) -> bool:
    """True when *path* is a whole filesystem / drive root.

    Such a root is refused as a grant target.  ``dirname`` of a top-level file
    is ``/``, so without this a click on "this directory" for ``/hosts`` would
    hand out the entire filesystem under a label that says otherwise.
    """
    if not path:
        return True
    parent = os.path.dirname(path)
    # os.path.dirname is idempotent at a root ("/" -> "/", "C:\\" -> "C:\\").
    return parent == path


def _within(child: str, root: str, *, subtree: bool) -> bool:
    """Path containment on two absolute, already-normalized realpaths.

    Compared byte-for-byte with a separator-terminated root, so a SIBLING whose
    name merely starts with the root's (``/srv/appdata`` against a grant for
    ``/srv/app``) does not match.  No case folding: on a case-sensitive
    filesystem two spellings are two different files, and on a case-insensitive
    one this only ever under-matches, which costs a prompt instead of granting a
    write.
    """
    if not child or not root:
        return False
    if child == root:
        return True
    if not subtree:
        return False
    return child.startswith(root.rstrip(os.sep) + os.sep)


def _is_externally_linked(real_target: str) -> bool:
    """True when *real_target* is an existing regular file with >1 hard link.

    ``realpath`` resolves symlinks but NOT hard links: a second name for the
    same inode can sit inside a granted root while the file's other name lives
    outside it, and a write through the inside name corrupts the outside one —
    silently, and a write is not undoable.  ``st_nlink`` cannot say WHERE the
    other names are, so any multiplicity is refused outright.  Failing closed
    here costs exactly one prompt (the pre-grant behaviour); the offer is
    withheld too, since a grant for an aliased file could never be honoured.

    Directories are exempt — their link count includes every subdirectory's
    ``..``.  A missing target is a new file: no alias can exist yet.  ``lstat``
    (not ``stat``): the leaf is already symlink-resolved, and following a link
    swapped in after resolution would grade a different inode than the one the
    write will hit.
    """
    try:
        st = os.lstat(real_target)
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and st.st_nlink > 1


class _ResolvedWrite(NamedTuple):
    """The verified facts about one write-tool permission request."""

    tool_key: str
    #: ``realpath`` of the target.  A symlink at the leaf resolves HERE, which is
    #: what makes ``granted_dir/link -> /etc/shadow`` fall outside the grant.
    real_target: str
    #: ``realpath`` of the target's directory, checked in ADDITION to the target
    #: so a grant cannot be satisfied through a linked ancestor either.
    real_parent: str


def _resolve(
    *,
    tool_kind: str,
    raw_params: Mapping | None,
    tool_name: str,
    mcp_server_name: str,
) -> _ResolvedWrite | None:
    """Verify a permission request is a single-target file write, or fail closed.

    Returns None — no offer, no match — unless every one of these holds:

    * the provenance-verified canonical identity (``_meta.kiro``, threaded here
      by the caller) names a BUILT-IN tool whose only governed capability is
      ``filesystem.write`` (see :data:`_WRITE_ONLY_BUILTIN_TOOLS`) — the
      agent-authored ``kind`` never classifies a request as a write;
    * the tool kind is the write kind (see :data:`WRITE_TOOL_KIND`) — a
      consistency check that can only withhold, never grant;
    * the canonical tool identity yields a key;
    * the bounded path walk completed (a TRUNCATED walk may have missed a
      second target, so it is unverifiable, not empty);
    * it found EXACTLY ONE path.  A batch write naming several files has no
      single "this directory", and picking one of them would grant a scope the
      label does not describe;
    * that path is absolute (a relative path needs a cwd this layer does not
      know, and guessing one is how a grant lands on the wrong tree) and carries
      no NUL byte;
    * the resolved target is not a multi-hard-linked regular file (see
      :func:`_is_externally_linked`).
    """
    if mcp_server_name or tool_name not in _WRITE_ONLY_BUILTIN_TOOLS:
        return None
    if tool_kind != WRITE_TOOL_KIND:
        return None
    tool_key = write_tool_trust_key(mcp_server_name, tool_name)
    if not tool_key:
        return None
    found = target_paths(raw_params)
    if found.truncated or len(found) != 1:
        return None
    requested = found[0]
    if "\x00" in requested or not os.path.isabs(requested):
        return None
    real_target = os.path.realpath(requested)
    real_parent = os.path.realpath(os.path.dirname(requested))
    if not real_target or not real_parent:
        return None
    if _is_externally_linked(real_target):
        return None
    return _ResolvedWrite(tool_key, real_target, real_parent)


def derive_write_grant_offer(
    *,
    tool_kind: str,
    raw_params: Mapping | None,
    tool_name: str,
    mcp_server_name: str,
    project: str = "",
) -> dict[str, str]:
    """Return the pending-card fields describing which path tiers may be offered.

    The returned roots are the SERVER's authority for a later grant: the client
    echoes one back as its consent proof and the handler stores only its own
    value, so a client cannot widen a grant by sending a different root.

    Keys, all absent when the tier is not offerable:

    ``write_tool_key``
        The tool identity every tier binds to.
    ``write_file_root`` / ``write_dir_root`` / ``write_ws_root``
        The realpath each tier would grant.  Each tier's label is built from
        its own root; there is no separate display-path field, so no wire
        surface exists that nothing reads.

    A tier is withheld rather than narrowed when it cannot be described
    honestly: the ``dir`` tier is absent when the file sits directly in a
    filesystem root, and the ``workspace`` tier is absent unless the session has
    a project directory that really does contain the target.  Withholding is the
    only safe direction — a tier the user cannot see is a prompt they answer
    once more, while a tier whose label overstates its root is consent obtained
    for something else.
    """
    resolved = _resolve(
        tool_kind=tool_kind,
        raw_params=raw_params,
        tool_name=tool_name,
        mcp_server_name=mcp_server_name,
    )
    if resolved is None:
        return {}
    out: dict[str, str] = {
        "write_tool_key": resolved.tool_key,
        "write_file_root": resolved.real_target,
    }
    # Same containment rule the workspace tier applies below: the tier must
    # actually CONTAIN the resolved write.  A leaf symlink (docs/README.md ->
    # ../README.md) resolves the target OUTSIDE the link's own directory, and a
    # card saying "writes in and under docs/" for a write that lands beside it
    # would be consent obtained for something else.
    if not _is_filesystem_root(resolved.real_parent) and _within(
        resolved.real_target, resolved.real_parent, subtree=True
    ):
        out["write_dir_root"] = resolved.real_parent
    if project and os.path.isabs(project) and "\x00" not in project:
        real_project = os.path.realpath(project)
        # The workspace tier must actually CONTAIN what the card is about.
        # Offering it for a write outside the project would let one click grant
        # a tree the request never touched.
        if (
            real_project
            and not _is_filesystem_root(real_project)
            and _within(resolved.real_target, real_project, subtree=True)
            and _within(resolved.real_parent, real_project, subtree=True)
        ):
            out["write_ws_root"] = real_project
    return out


def match_write_grant(
    *,
    tool_kind: str,
    raw_params: Mapping | None,
    tool_name: str,
    mcp_server_name: str,
    grants: set[WriteGrant],
) -> WriteGrant | None:
    """Return the grant that authorizes this write request, or None.

    Both the target AND its directory must fall inside the grant's root.  The
    target catches a symlink at the leaf; the directory catches a linked
    ancestor.  Either check alone leaves the other escape open, and a write is
    not undoable, so both run.  A hard-linked target never reaches the loop at
    all — :func:`_resolve` refuses it (see :func:`_is_externally_linked`).

    A ``file``-scope grant (``subtree`` False) matches only its exact realpath,
    so it cannot be spent on a neighbouring file in the same directory.
    """
    if not grants:
        return None
    resolved = _resolve(
        tool_kind=tool_kind,
        raw_params=raw_params,
        tool_name=tool_name,
        mcp_server_name=mcp_server_name,
    )
    if resolved is None:
        return None
    for grant in grants:
        if grant.tool_key != resolved.tool_key or not grant.root:
            continue
        if not _within(resolved.real_target, grant.root, subtree=grant.subtree):
            continue
        # For the exact-file tier the parent check is implied by the target
        # match; for a subtree grant it is the ancestor-symlink guard.
        if grant.subtree and not _within(resolved.real_parent, grant.root, subtree=True):
            continue
        return grant
    return None


#: Client decision name -> (pending-card field holding the root, subtree?).
#: The handler reads the root ONLY from this table, so a decision name can never
#: address a field it was not built for.
WRITE_GRANT_DECISIONS: dict[str, tuple[str, bool]] = {
    "trust_path_file": ("write_file_root", False),
    "trust_path_dir": ("write_dir_root", True),
    "trust_path_ws": ("write_ws_root", True),
}
