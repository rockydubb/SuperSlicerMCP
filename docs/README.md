# SuperSlicerMCP documentation

Development documentation for this fork, mirrored to the Obsidian vault at
`Obsidian_Dubb/10-Interests/108-Software-Development/108.4-SuperSlicerMCP/01-Development Documentation`.
Every substantive change gets written to the matching subfolder in both places.

Note the naming: upstream SuperSlicer already ships a `doc/` folder (singular)
holding its own build guides. This `docs/` tree is ours and will not collide
with upstream on merge or rebase.

## Folder taxonomy

| Folder | Put here |
|--------|----------|
| `architecture/` | How subsystems work and fit together; component and data-flow docs. |
| `decisions/` | ADRs. A chosen approach and why, alternatives rejected. `ADR-NNN-title.md`. |
| `implementation-logs/` | Dated record of what was built or changed in a work session. `YYYY-MM-DD-topic.md`. |
| `runbooks/` | Step-by-step operational procedures (build, release, recovery). |
| `audits/` | Reviews, deep dives, assessments. |
| `product/` | Product notes and feature briefs. |
| `user-guides/` | End-user facing how-tos. |
| `superpowers/` | Skill and agent workflow notes, plans, specs. |
| `prompts/` | Reusable prompts: session handoffs, agent briefings. |
| `todo/` | Deferred follow-ups and pending work. |
| `assets/` | Images, diagrams, binary attachments referenced by docs. |
| `archive/` | Superseded notes kept for history. |

## What this project is

A SuperSlicer build with an MCP server wired into it, so an AI assistant can
drive the slicer directly: read and write configuration, manage presets, and
trigger slicing over a local TCP socket.

The MCP work is not ours. It was written by guysoft on a feature branch of his
SuperSlicer fork. What we did was move it onto the newest mainline SuperSlicer
commit. See `decisions/ADR-001-port-mcp-onto-latest-mainline.md`.

## Start here

- `architecture/mcp-configserver-architecture.md` for how the two halves talk.
- `decisions/ADR-001-port-mcp-onto-latest-mainline.md` for why the repo is laid out this way.
- `runbooks/build-macos.md` before attempting a build.
- `implementation-logs/2026-08-08-fork-setup-and-mcp-port.md` for the full record of session one.
- `todo/open-items.md` for what is still unresolved.

## Branches

| Branch | What it is |
|--------|-----------|
| `master_27` | Untouched mainline SuperSlicer. Reference copy, do not commit here. |
| `mcp-on-latest` | The working branch. MCP feature cherry-picked onto latest `master_27`. |

`origin` is `rockydubb/SuperSlicerMCP`. `upstream` is `guysoft/SuperSlicer`, with
its push URL set to `DISABLED` so nothing can be pushed there by accident.
