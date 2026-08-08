# ADR-001: Port the MCP feature onto latest mainline instead of building guysoft's branch

Date: 2026-08-08
Status: accepted

## Context

The goal is a SuperSlicer build with an MCP server in it, to help debug a 3D
printer. The MCP work exists only on `feature/config_server` in
`guysoft/SuperSlicer`. Mainline `supermerill/SuperSlicer` has none of it, verified
by a code search returning zero hits.

That branch is based on SuperSlicer 2.7.61.10, branch point `30a215731` from
2025-09-16. Mainline `master_27` is at 2.7.62.0, HEAD `1f3d287e9` from
2025-11-18. The branch is 141 commits behind mainline and 20 ahead.

Three options were on the table.

1. Build `feature/config_server` as-is on the older base.
2. Fork mainline separately and rebuild the MCP feature there.
3. Cherry-pick the MCP commits onto the existing clone's `master_27`.

## Decision

Option 3. A branch `mcp-on-latest` carrying the five MCP commits on top of
`1f3d287e9`.

## Why

Option 2 was the original proposal and it turned out to be unnecessary. The HEAD
of `guysoft/SuperSlicer:master_27` and the HEAD of
`supermerill/SuperSlicer:master_27` are the same commit, `1f3d287e9`. guysoft
never modified master_27, he only added a side branch. Mainline code was already
on disk. A separate fork of supermerill would have produced a second copy of
identical bytes, and would then have needed guysoft added as a second remote to
reach the MCP work anyway. Keeping the fork parented on guysoft is strictly
better: `upstream` already points where the feature lives.

Option 1 was rejected once option 3 proved free. The reason to prefer it was risk
avoidance, and that reason evaporated when all five cherry-picks applied without
conflict.

The port is cheap because of how the feature is shaped. Two new files carry
almost all of it, `ConfigServer.cpp` at roughly 1000 lines and `ConfigServer.hpp`,
and new files cannot conflict. Edits to pre-existing files total about 100 lines
across seven files: `PrusaSlicer.cpp`, `PrintConfig.cpp`, `GUI_App.cpp`,
`GUI_App.hpp`, `GUI_Init.hpp`, `Preferences.cpp`, and two CMakeLists.

## How it was validated

The cherry-picks ran in a throwaway worktree off `upstream/master_27` before
anything touched the working tree. All five clean.

Post-port checks confirmed the build wiring survived: `ConfigServer.cpp` and
`.hpp` listed at `src/slic3r/CMakeLists.txt:381-382`, `test_config_server.cpp`
registered at `tests/libslic3r/CMakeLists.txt:49`, the `enable-config-server`
option defined at `src/libslic3r/PrintConfig.cpp:12019` and parsed at
`src/PrusaSlicer.cpp:225`.

Then a drift check, because a clean cherry-pick proves the absence of textual
conflict and nothing about whether the code still compiles. `ConfigServer.cpp`
calls into the application at five points: `wxGetApp().plater`, `.mainframe`,
`.get_tab`, `.preset_bundle`, `.CallAfter`. All five exist in `GUI_App.hpp` on
the new base. These are long-lived PrusaSlicer APIs unlikely to have moved in 141
commits.

## Commits excluded

`b77c19df9`, "Code to make it to work, not sure if needed", only touches
`src/libslic3r/GCode/SeamPlacer.hpp`. Unrelated to MCP, and the commit message
says the author did not know what it did. Revisit only if the build fails in a
way that points there.

The three dependency fixes from 2026-03-19 were also left out: MPFR automake
version mismatch, static libpng resolution, GCC 15 `-Wtemplate-body` suppression.
All Linux and GCC oriented, and the target here is arm64 macOS with Clang. Worth
revisiting if the dependency stage fails.

## Consequences

The gain is modest and worth stating honestly. 2.7.61.10 to 2.7.62.0-beta2 is
141 commits and two months, beta to beta. Mainline `master_27` has not moved
since November 2025. The reason to take the newer base is that it cost nothing,
not that it delivers much.

Costs and obligations that follow:

- The build is unverified. Nothing has been compiled. This is the open risk.
- The branch diverges from guysoft's, so his later fixes do not arrive for free.
  Any future fix of his has to be cherry-picked deliberately.
- If a build failure appears that guysoft's branch does not have, `master_27` is
  still checked in untouched as a reference point, and falling back to building
  `upstream/feature/config_server` directly remains available.

## Repository layout that follows

| Branch | Role |
|---|---|
| `master_27` | Untouched mainline. Reference only, no commits. |
| `mcp-on-latest` | Working branch. Pushed to `origin`. |

`origin` is `rockydubb/SuperSlicerMCP`. `upstream` is `guysoft/SuperSlicer` with
its push URL set to `DISABLED`.
