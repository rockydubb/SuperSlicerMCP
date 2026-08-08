# CLAUDE.md

Read `docs/README.md` and `docs/todo/open-items.md` before starting work. They
carry the state this file summarises.

## What this repo is

A fork of SuperSlicer carrying an MCP server, so an AI assistant can drive the
slicer over a local HTTP socket. The MCP code is guysoft's, taken from
`feature/config_server` on his fork and cherry-picked onto the newest mainline
SuperSlicer commit.

## Branches

| Branch | Role |
|---|---|
| `mcp-on-latest` | Working branch. Commit here. |
| `master_27` | Untouched mainline reference. Do not commit here. |

`origin` is `rockydubb/SuperSlicerMCP`. `upstream` is `guysoft/SuperSlicer` with
its push URL set to `DISABLED` on purpose. Leave it that way.

## Do not trust MCP_INTEGRATION_STATUS.md

That file is inherited from guysoft's branch and is out of date. It claims the
ConfigServer is not integrated into the build and instructs you to apply
`integrate_configserver.patch` from `/home/guy/tmp/SuperSlicer`. The patch does
not exist in the tree, the path is another machine, and the integration is
already committed. Use `FASTMCP_README.md`.

Same caution applies to `MCP_README.md`, which points at `mcp_server.py`. The live
server is `superslicer_fastmcp_server.py`.

## Build state

Nothing has been compiled. The port rests on five clean cherry-picks, which prove
no textual conflict and nothing about whether it builds. Treat a successful
compile as unproven until you have one.

Follow `docs/runbooks/build-macos.md`. The short version: install cmake, move the
repo out of iCloud, run `./BuildMacOS.sh -d -a` alone before
`./BuildMacOS.sh -s -a`, and expect trouble from the hardcoded 10.14 deployment
target against a macOS 26 SDK.

## Where the MCP code lives

C++ half, compiled into the binary:

- `src/slic3r/Utils/ConfigServer.cpp` and `.hpp`, a Boost.Asio and Beast HTTP
  server on port 21987
- registered at `src/slic3r/CMakeLists.txt:381-382`
- CLI option at `src/libslic3r/PrintConfig.cpp`, parsed in `src/PrusaSlicer.cpp`
- lifecycle in `src/slic3r/GUI/GUI_App.cpp`, preferences in `Preferences.cpp`
- tests at `tests/libslic3r/test_config_server.cpp`

Python half:

- `superslicer_fastmcp_server.py`, 25 MCP tools
- `run_mcp_server.sh`, `requirements-mcp.txt`

Enable with `superslicer --enable-config-server`, or the AppConfig keys
`enable_config_server_at_startup` and `config_server_port`.

`docs/architecture/mcp-configserver-architecture.md` has the endpoint and tool
inventory.

## Threading rule

`ConfigServer` runs on its own thread and wxWidgets is not thread-safe. Any GUI
mutation goes through `wxGetApp().CallAfter`. Do not call into `plater`,
`mainframe`, `get_tab` or `preset_bundle` directly from a request handler without
it.

## Security

The server has no authentication and no TLS, and it can write configuration and
load files. Loopback only. `FASTMCP_README.md` shows a `uvicorn --host 0.0.0.0`
invocation; do not use it.

## Documentation workflow

Every substantive change gets written to the matching subfolder of `docs/` and
mirrored to the Obsidian vault at:

```
~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian_Dubb/10-Interests/108-Software-Development/108.4-SuperSlicerMCP/01-Development Documentation/
```

Both places, same relative path. `docs/README.md` has the routing table:
architecture, decisions (ADRs), implementation-logs (`YYYY-MM-DD-topic.md`),
runbooks, audits, product, user-guides, superpowers, todo, assets, archive.

Note that upstream ships its own `doc/` folder, singular. That one is theirs.
`docs/` is ours.

## Prose style

Documentation and vault notes follow `~/.claude/CLAUDE.md`: no em dashes, straight
quotes only, no banned vocabulary, no closing summary sections. Code, commit
messages and CLI output are exempt.
