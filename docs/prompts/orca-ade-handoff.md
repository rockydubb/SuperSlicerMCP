# Handoff prompt: Orca ADE session

Paste this into a fresh Claude Code session after adding the repo to Orca. It
brings a cold agent up to the state at the end of the 2026-08-08 session and puts
it on the build.

The prompt carries the critical facts inline rather than only pointing at `docs/`,
so it still works if the docs did not reach the worktree. It also tells the agent
to stop if they are missing, which is the failure mode worth catching early.

Written 2026-08-08. Update the "State" and "What I want you to do now" sections
once a build has actually been attempted, otherwise a later session will be told
to run a dependency stage that already ran.

## The prompt

```text
Read CLAUDE.md and docs/README.md first, then docs/todo/open-items.md. If those
files are missing, this is a fresh worktree that didn't get the untracked docs.
Say so and stop.

Context you need up front:

This is a fork of SuperSlicer carrying an MCP server, so an AI assistant can drive
the slicer over local HTTP. Goal is debugging a 3D printer. The MCP code is
guysoft's, from `feature/config_server` on his fork, cherry-picked onto the newest
mainline SuperSlicer commit.

State:
- Working branch is `mcp-on-latest`, 5 commits on top of mainline `1f3d287e9`.
  Commit here. `master_27` is an untouched mainline reference, do not commit there.
- `origin` = rockydubb/SuperSlicerMCP. `upstream` = guysoft/SuperSlicer with its
  push URL set to DISABLED on purpose. Leave it.
- Nothing has been compiled. The port rests on 5 clean cherry-picks, which prove
  no textual conflict and nothing about whether it builds. Assume unproven.

Three traps that will waste your time:
1. MCP_INTEGRATION_STATUS.md is stale. It says ConfigServer "is not yet integrated
   into the SuperSlicer build" and tells you to apply integrate_configserver.patch
   from /home/guy/tmp/SuperSlicer. That patch is not in the tree, the path is
   another machine, and the integration is already committed
   (src/slic3r/CMakeLists.txt:381-382). Use FASTMCP_README.md instead.
2. MCP_README.md points at mcp_server.py. That file has zero MCP tool decorators
   and looks abandoned. The live server is superslicer_fastmcp_server.py, 25 tools.
3. BuildMacOS.sh hardcodes CMAKE_OSX_DEPLOYMENT_TARGET=10.14 at four places
   (lines 264, 267, 393, 395). Host is macOS 26.5 / Xcode 26.6. Expect
   dependency-stage symbol failures. Raise the target instead of fighting it.

Architecture, so you don't re-derive it:
Claude --MCP--> superslicer_fastmcp_server.py --HTTP 127.0.0.1:21987--> ConfigServer
(C++, Boost.Asio + Beast, compiled into the binary). Five endpoints: /api/config,
/api/presets, /api/status, /api/command, /api/list_instances. Eight commands behind
/api/command. Off by default; enable with `superslicer --enable-config-server` or
the AppConfig keys enable_config_server_at_startup and config_server_port.
ConfigServer runs on its own thread and wxWidgets is not thread-safe, so every GUI
mutation goes through wxGetApp().CallAfter. Do not call plater, mainframe,
get_tab or preset_bundle directly from a request handler.
If 21987 is taken it walks up to 10 ports, and each instance writes a descriptor to
superslicer_instances/ in the temp dir. "Didn't start" and "is on 21988" look
identical unless you check both.

What I want you to do now, in this order:
1. Confirm you're on `mcp-on-latest` and the tree is clean.
2. Verify the repo is NOT inside iCloud Drive. If it is, stop and tell me. A
   build will sync every object file as it's written and can corrupt mid-build.
3. Check cmake is installed (`brew install cmake` if not; BuildMacOS.sh aborts
   without it).
4. Run the dependency stage ALONE first: ./BuildMacOS.sh -d -a
   Do not chain the slicer build. Deps is the long, failure-prone stage and I want
   its failure readable. Report what breaks before attempting a fix.

Do not skip to step 4. Do not "fix" things I haven't asked about. Do not touch
git remotes.

Documentation rule: every substantive change gets written to the matching
subfolder of docs/ AND mirrored to the same relative path under
~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian_Dubb/10-Interests/108-Software-Development/108.4-SuperSlicerMCP/01-Development Documentation/
Build attempts go in docs/implementation-logs/YYYY-MM-DD-topic.md. Update
docs/runbooks/build-macos.md with what actually happens, since it currently
records predictions, not results.
Prose style follows ~/.claude/CLAUDE.md: no em dashes, straight quotes only.
```

## Why the ordering is spelled out

An agent handed a build task will normally run the whole thing, hit a dependency
wall an hour in, and start editing CMake files unprompted. Steps 2 and 3 cost
seconds and both are live blockers as of writing: the repo is still in iCloud and
cmake is not installed.
