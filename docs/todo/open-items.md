# Open items

Updated 2026-08-08, after the first dependency-stage build.

## Blocking

**OpenVDB will not compile under Apple Clang 26.** The only dependency that
fails. `NodeManager.h` lines 330, 350 and 375 write `OpT::template eval(...)`
with no argument list, and
`-Wmissing-template-arg-list-after-template-kw` is a default error in this
compiler. Fix is drafted but not applied, see
`runbooks/build-macos.md`. Nothing downstream can proceed until this clears.

**The slicer itself is still uncompiled.** The dependency stage got 21 of 22
libraries built, which says the dependency stack is nearly sound and still says
nothing about whether the MCP port compiles. `mcp-on-latest` stays unverified.

## Resolved

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

## Expected to bite

**`fastmcp>=0.1.0` in `requirements-mcp.txt`.** That floor predates FastMCP's
later API. A fresh `pip install` will pull something
`superslicer_fastmcp_server.py` was not written against, and the failure will look
like import errors or unknown decorator arguments rather than anything obviously
version related. Pin to whatever version guysoft actually used, once determined.
Python here is 3.14.6, which is also newer than anything that script was tested
on.

**Dependency rot generally.** guysoft's last three commits were all deps fixes.
Budget for a few rounds.

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
and no TLS, and it can load files and write config. Fine on 127.0.0.1 for a
single user. `FASTMCP_README.md` documents a `uvicorn --host 0.0.0.0` invocation
that should not be used as written.

**Upstream contribution.** The port applies cleanly to mainline, so it could go to
supermerill as a PR. Mainline has been dormant since November 2025, so expectations
should be low. Not a priority while the printer problem is unsolved.
