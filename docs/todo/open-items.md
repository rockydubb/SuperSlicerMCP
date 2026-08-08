# Open items

Updated 2026-08-08, after the first dependency-stage build.

## Blocking

Nothing. The C++ half builds, runs and is verified.

## Parked by decision

**The Python MCP layer is broken and work on it has stopped.** See
`decisions/ADR-002-stop-work-on-python-mcp-layer.md`. It is written against
FastMCP 0.x and dies on first import under 3.4.6, plus three further certain
breakages, a missing `httpx` dependency, an `asyncio` PyPI pin that shadows the
stdlib, and HTTP transport where Claude Code needs stdio. It is a rewrite, not
a version bump.

`superslicer_fastmcp_server.py`, `run_mcp_server.sh` and
`requirements-mcp.txt` are left in the tree, untouched and known broken.

Use the stock CLI at
`/Applications/SuperSlicer.app/Contents/MacOS/SuperSlicer` instead. 40 options,
636 config settings via `--help-fff`, verified headless.

## Resolved

**ConfigServer now binds to loopback.** Was
`tcp::endpoint(tcp::v4(), current_port)`, which is `INADDR_ANY`, so the
unauthenticated write-capable API was reachable from the LAN. Now
`make_address("127.0.0.1")`. Verified: `lsof` reports `127.0.0.1:21987`,
loopback returns 200, and the machine's LAN address is refused.

**The port builds and runs.** Both stages exit 0. 93MB arm64 binary at
`build/bin/superslicer`. All five ConfigServer endpoints return 200, including
`/api/config` with 194KB of annotated keys. `mcp-on-latest` is no longer
unverified. See
`implementation-logs/2026-08-08-first-successful-build-and-configserver-smoke-test.md`.

**OpenVDB under Apple Clang 26.** Fixed in `deps/+OpenVDB/OpenVDB.cmake` by
demoting `-Wmissing-template-arg-list-after-template-kw` to a warning on Apple
only, preserving `DEP_WERRORS_SDK`. The one dependency fix the whole stack
needed.

**Use a separate datadir.** First launch tried to migrate
`~/Library/Application Support/SuperSlicer`, the production install's directory,
and failed on a missing `snapshots` folder. Run with
`--datadir ~/Developer/superslicer-dev-data` rather than creating the folder.
Keeps an unproven beta away from real printer profiles.

**cmake.** Installed, 4.4.2 via Homebrew. CMake 4 drops support for
`cmake_minimum_required(VERSION <3.5)` and this tree has two below that floor,
but `BuildMacOS.sh:16` already exports `CMAKE_POLICY_VERSION_MINIMUM=3.5` and
both built clean.

**Repo out of iCloud.** Now at `~/Developer/SuperSlicerMCP`. Copied rather than
moved, so the iCloud original survives as a fallback but is behind as of
`dbef7d6ae`. The dependency stage wrote 5.8G, which vindicates the move.

**Docs tree committed.** `CLAUDE.md` and `docs/` were untracked and would not
have survived a clone. Committed in `dbef7d6ae`, which also added a `!docs/**`
exception to `.gitignore`, because the inherited `build*` rule was matching
`docs/runbooks/build-macos.md` at depth.

## Ruled out

**Deployment target 10.14 against the macOS 26 SDK.** Predicted to be the main
source of dependency-stage breakage. It is not. Twenty-one dependencies built
against the macOS 26 SDK with `-mmacosx-version-min=10.14`, and the three
`-Werror=` availability guards at `deps/CMakeLists.txt:121` that exist to catch
this exact mismatch never fired. Leave the target alone.

## Confirmed, no longer predictions

**`fastmcp>=0.1.0` was the problem, and it is worse than a floor.** Measured on
FastMCP 3.4.6: first import raises
`TypeError: FastMCP() got unexpected keyword argument(s): 'dependencies'`, plus
`@mcp.server.start()` / `@mcp.server.stop()` (lines 913, 925) and
`app = mcp.app` (line 931) all target APIs that no longer exist. `httpx` is
imported at line 37 and missing from requirements. `asyncio>=3.4.3` in
requirements is an abandoned PyPI package shadowing the stdlib. Parked, see
ADR-002.

**Dependency rot was one fix, not several.** guysoft's last three commits were
all Linux deps fixes and the runbook budgeted for "a few rounds" of the macOS
equivalent. Only OpenVDB needed anything. The other 21 built unmodified.

## Questions to resolve

**What does `b77c19df9` do?** "Code to make it to work, not sure if needed",
touching only `src/libslic3r/GCode/SeamPlacer.hpp`. Excluded from the port. If the
build fails somewhere near seam placement, start here.

**Which of the two Python servers is canonical?** `superslicer_fastmcp_server.py`
(31KB, 25 MCP tools) is clearly the live one. `mcp_server.py` (15KB, 416 lines,
no tool decorators) has no decorators and looks superseded. Confirm, then move the
dead one to `docs/archive/` or delete it, because `MCP_README.md` still points at
it and that will mislead.

**Are `handle_list_config_keys` and `handle_list_instances` reachable?** Both are
declared in `ConfigServer.hpp` and defined in the `.cpp`, but neither appears in
the eight-way `command` dispatch. `list_instances` is served by its own HTTP
endpoint. `list_config_keys` may be dead code, which matters because the Python
`search_config` tool likely wants it.

## Deferred

**Rebase versus cherry-pick going forward.** `mcp-on-latest` now diverges from
`upstream/feature/config_server`. If guysoft ships more fixes they have to be
picked deliberately. No automation for this, and probably not worth building for a
branch that has been quiet since March.

**Security hardening if this ever leaves loopback.** The ConfigServer has no auth
and no TLS, and it can load files and write config. Now genuinely bound to
127.0.0.1, which is fine for a single user. Two places still document or set
`0.0.0.0` and should not be followed: `FASTMCP_README.md`, and
`run_mcp_server.sh` itself, which defaults `MCP_SERVER_HOST` to `0.0.0.0`.

**Thin stdio MCP server over the CLI.** The better shape if invoking the CLI
directly becomes the bottleneck. Roughly 150 lines against current FastMCP,
shelling out to the stock app binary. No C++ fork, no listener, no upstream
divergence. Deferred, not rejected. See ADR-002.

**Build artifacts are untracked but noisy.** `version.date.inc`,
`cmake/CPackConfig.cmake` and 20 generated `resources/localization/*/SuperSlicer.mo`
files appear in every `git status` after a build. None are committed. A
`.gitignore` entry would quiet them.

**Upstream contribution.** The port applies cleanly to mainline, so it could go to
supermerill as a PR. Mainline has been dormant since November 2025, so expectations
should be low. Not a priority while the printer problem is unsolved.
