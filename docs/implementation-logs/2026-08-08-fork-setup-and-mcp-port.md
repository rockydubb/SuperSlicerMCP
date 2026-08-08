# 2026-08-08 - Fork setup and MCP port onto latest mainline

## Summary

Cloned the SuperSlicerMCP fork into the project directory, worked out where the
MCP server code actually lives, and moved it from an older SuperSlicer base onto
the newest mainline commit. Result is a branch `mcp-on-latest` that builds MCP
support on top of current SuperSlicer instead of the September 2025 snapshot
guysoft was working from.

No build attempted yet. cmake is not installed on this machine.

## Starting state

The directory `08-SuperSlicerMCP/00-main` had been `git init`ed but was
otherwise empty: branch `master`, zero commits, zero tracked files, zero
untracked files, no remote. Nothing to preserve.

## Clone

Removed the empty `.git` (an empty repo still counts as a non-empty directory to
`git clone`, which refuses to clone into one), then:

```bash
gh repo clone rockydubb/SuperSlicerMCP .
```

`gh` set both remotes automatically because the target is a fork:

- `origin` = `https://github.com/rockydubb/SuperSlicerMCP.git`
- `upstream` = `https://github.com/guysoft/SuperSlicer.git`

Set the upstream push URL to `DISABLED` as a guard:

```bash
git remote set-url --push upstream DISABLED
```

Fork metadata: created 2026-08-08, parent `guysoft/SuperSlicer`, default branch
`master_27`. The fork copied only the default branch, so `feature/config_server`
was not in `origin`.

## Finding the MCP code

The checked-out `master_27` has no MCP content at all. A `git grep -i mcp` over
tracked markdown returned only `memcpy` hits inside `src/miniz`. A code search
across `supermerill/SuperSlicer` for MCP returned zero results, so mainline has
none of it either.

`guysoft/SuperSlicer` has two branches:

```
master_27              exact mirror of mainline, no MCP content
feature/config_server  all the MCP work
```

Fetched the branch explicitly:

```bash
git fetch upstream 'refs/heads/feature/config_server:refs/remotes/upstream/feature/config_server'
```

## Version comparison

| | `feature/config_server` | `master_27` |
|---|---|---|
| `version.inc` | `SLIC3R_VERSION_FULL 2.7.61.10` | `2.7.62.0` |
| branch point | `30a215731`, 2025-09-16 | n/a |
| newest commit | `cd616da36`, 2026-03-19 | `1f3d287e9`, 2025-11-18 |
| relative to mainline | 141 commits behind, 20 ahead | identical |

`guysoft/SuperSlicer:master_27` HEAD and `supermerill/SuperSlicer:master_27` HEAD
are both `1f3d287e9`. Same commit. guysoft never modified master_27, he only
added a side branch, which means the clone already contained mainline code.

Mainline's newest release is tag `2.7.62.0-beta2`, titled "2.7.63.0 beta 2",
published 2025-11-19. Mainline `master_27` has not moved since 2025-11-18. The
repo shows pushes into May 2026 but those went to other branches.

So `feature/config_server` sits on a base about two months older than the newest
SuperSlicer that exists. The commit dates on it run later (to March 2026) because
guysoft kept working without rebasing.

## What the 20 branch-only commits contain

Six touch MCP. Three are dependency build fixes from 2026-03-19 (MPFR automake
version mismatch, static libpng resolution, GCC 15 `-Wtemplate-body` suppression),
which suggests guysoft was fighting dependency rot in March. The rest are
upstream merge commits he pulled in.

The MCP commits and their C++ footprint:

| Commit | Subject | Existing files touched |
|---|---|---|
| `0951ea4d9` | Add config http server support on port 21987 | `PrusaSlicer.cpp` +11, `PrintConfig.cpp` +6, `GUI_App.cpp` +31, `GUI_App.hpp` +4, `GUI_Init.hpp` +1 |
| `c34c1b254` | Multi-instance support, port auto-increment, preferences UI | `GUI_App.cpp` +8, `Preferences.cpp` +41 |
| `bf43ba66f` | ConfigServer unit tests | tests CMakeLists |
| `87e13125f` | MCP server Python tooling | none |
| `7d8550389` | ConfigServer and MCP integration documentation | none |

Plus two new C++ files nothing can conflict with: `src/slic3r/Utils/ConfigServer.cpp`
(738 lines, then +305 in the multi-instance commit) and `ConfigServer.hpp`.

Total edits to pre-existing files come to roughly 100 lines across seven files.
That is why the port was cheap.

One commit deliberately excluded: `b77c19df9`, "Code to make it to work, not sure
if needed". It only touches `src/libslic3r/GCode/SeamPlacer.hpp` and has nothing
to do with MCP. The author did not know what it did.

## The port

Built it in a throwaway worktree first rather than guessing whether it would
apply:

```bash
git worktree add --detach /tmp/ss-port upstream/master_27
cd /tmp/ss-port && git switch -c mcp-on-latest
git cherry-pick -x 0951ea4d9 c34c1b254 bf43ba66f 87e13125f 7d8550389
```

All five applied clean. Zero conflicts.

Verified the wiring survived on the new base:

- `src/slic3r/CMakeLists.txt:381-382` lists `Utils/ConfigServer.cpp` and `.hpp`
- `tests/libslic3r/CMakeLists.txt:49` registers `test_config_server.cpp`
- `src/libslic3r/PrintConfig.cpp:12019` defines the `enable-config-server` option
- `src/PrusaSlicer.cpp:225` parses the flag

Checked for API drift, since a clean cherry-pick proves no textual conflict and
nothing more. `ConfigServer.cpp` reaches into the app at five call sites:
`wxGetApp().plater`, `.mainframe`, `.get_tab`, `.preset_bundle`, `.CallAfter`.
All five are still present in `GUI_App.hpp` on the new base. These are long-lived
PrusaSlicer APIs, so drift risk is low, but only a compile will settle it.

Removed the temp worktree, checked the branch out in the main tree, pushed:

```bash
git worktree remove --force /tmp/ss-port && git worktree prune
git checkout mcp-on-latest
git push -u origin mcp-on-latest
```

Final branch:

```
fa81741c4  Add ConfigServer and MCP integration documentation
090c42cb3  Add MCP server Python tooling for external ConfigServer access
b3ab30c54  Add ConfigServer unit tests
5e1c34eb2  Add multi-instance support, port auto-increment, and preferences UI
05882ec52  Add config http server support on port 21987
1f3d287e9  try build on macos15-intel        <- latest mainline
```

## Build environment findings

Inspected `BuildMacOS.sh` and the host. Four things stand in the way:

1. cmake is not installed. The script aborts at line 73 without it.
2. `CMAKE_OSX_DEPLOYMENT_TARGET` is hardcoded to `10.14` at lines 264, 267, 393
   and 395. The host runs macOS 26.5 with the Xcode 26.6 SDK. Twelve major
   versions of gap.
3. Lines 160 to 167 `ls` into `/Applications/Xcode_14.3.1.app` and
   `Xcode_15.2.0.app`. Those are GitHub CI runner paths. Harmless in themselves,
   but they show the script was tuned for Xcode 14 and 15.
4. The repo lives in iCloud Drive. 349M of `.git` and 501M total, about to
   produce a full dependency stack plus a thousand-odd object files inside a
   synced folder.

Host: macOS 26.5 build 25F71, arm64, Xcode 26.6 build 17F113, 18 cores, 892Gi
free on the data volume, Python 3.14.6.

`BuildMacOS.sh` flags: `-w` wipe, `-d` deps, `-r` clean deps build files, `-a`
arm64, `-x` x86_64, `-b` debug symbols, `-c` XCode project, `-s` build the
slicer, `-t` tests (with `-s`), `-i` DMG, `-v` replace the `UNKNOWN` version
with today's date.

## Documentation trap

`MCP_INTEGRATION_STATUS.md` on the branch is stale and will mislead anyone who
follows it. It states the ConfigServer "is not yet integrated into the
SuperSlicer build" and gives as step one:

```bash
cd /home/guy/tmp/SuperSlicer
patch -p1 < integrate_configserver.patch
```

That patch is not in the tree, and the integration is already committed. The
path is guysoft's own machine. Use `FASTMCP_README.md` instead.

## Not done

Nothing has been compiled. See `todo/open-items.md`.
