# Open items

Updated 2026-08-08, after the first dependency-stage build.

## Blocking

**ConfigServer binds to 0.0.0.0, not loopback.** `ConfigServer.cpp:64` uses
`tcp::endpoint(tcp::v4(), current_port)`, which is `INADDR_ANY`. Confirmed by
`lsof` reporting `*:21987` and by a 200 response on `http://0.0.0.0:21987`. No
auth, no TLS, and the API writes configuration and loads files, so this is an
unauthenticated write-capable API exposed to the local network. `CLAUDE.md`
asserts loopback only; that is intent, not what the code does. Fix is one line:

```cpp
tcp::endpoint(boost::asio::ip::make_address("127.0.0.1"), current_port)
```

**Python half untested.** `requirements-mcp.txt` floors `fastmcp>=0.1.0`, see
below. Nothing has installed or run it yet, so the Claude-to-slicer path is
unproven end to end even though the HTTP half works.

## Resolved

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
