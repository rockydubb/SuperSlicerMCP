# ADR-002: Stop work on the Python MCP layer, use the SuperSlicer CLI

Date: 2026-08-08
Status: Accepted

## Context

The fork now builds and the C++ half works. `mcp-on-latest` compiles clean, the
ConfigServer listens on loopback, and all five HTTP endpoints return 200. See
`../implementation-logs/2026-08-08-first-successful-build-and-configserver-smoke-test.md`.

The Python half is the remaining piece. It is `superslicer_fastmcp_server.py`,
25 tools, written against FastMCP 0.x. The current release is FastMCP 3.4.6.

Testing it in a fresh venv on Python 3.13 with `fastmcp 3.4.6`, `mcp 1.29.0`,
`httpx 0.28.1`, the first import fails:

```
TypeError: FastMCP() got unexpected keyword argument(s): 'dependencies'
```

That is the first break the interpreter reaches, not the only one. Reading
ahead:

- `@mcp.server.start()` and `@mcp.server.stop()` at lines 913 and 925. The
  `mcp.server` decorator namespace does not exist in modern FastMCP.
- `app = mcp.app` at line 931. Removed. Modern FastMCP exposes `http_app()` or
  `mcp.run()`.
- `httpx` is imported at line 37 and is absent from `requirements-mcp.txt`.
- `requirements-mcp.txt` pins `asyncio>=3.4.3`, a real but abandoned PyPI
  package that shadows the stdlib module.
- `run_mcp_server.sh` binds the MCP server to `0.0.0.0`, and instructs the user
  to apply `integrate_configserver.patch`, which does not exist in the tree.

There is also an architectural mismatch independent of the breakage.
`run_mcp_server.sh` runs uvicorn on port 3000, which is HTTP transport. Claude
Code attaches to MCP servers over stdio. Even fully repaired, that script
produces a server Claude Code cannot connect to without further change.

So this is a rewrite of the transport and lifecycle layer against a framework
three major versions removed from what it was written for, not a version bump.

## What the alternative already provides

The stock SuperSlicer at `/Applications/SuperSlicer.app/Contents/MacOS/SuperSlicer`,
version 2.7.61.10, has a full headless CLI. Measured on this machine:

- 40 top-level options
- 636 print and G-code configuration options via `--help-fff`, each settable
  inline
- Actions: `--slice`, `--export-gcode`, `--export-3mf`, `--export-stl`,
  `--export-obj`, `--export-amf`, `--info`, `--save`, `--gcodeviewer`
- `--load`, `--output`, `--datadir`, `--threads`, `--loglevel`

Verified working headless:

```bash
/Applications/SuperSlicer.app/Contents/MacOS/SuperSlicer \
  --info resources/shapes/sphere.stl
```

Returns dimensions, facet count, manifold status and volume. Exit 0, no window.

Printer profiles are also plain ini files under
`~/Library/Application Support/SuperSlicer/{print,filament,printer,physical_printer}`,
so enumerating and reading presets needs no API at all.

## Decision

Stop work on the Python MCP layer. Drive the slicer through the stock CLI
instead, invoked directly.

The immediate goal is debugging a 3D printer. That work is dominated by
sweeping settings across many slices and comparing the G-code, which the CLI
does better than an HTTP API: headless, scriptable, reproducible, no listener,
and nothing to maintain against upstream.

## Consequences

What is given up: control of a running GUI instance. Reading and mutating the
state of an open SuperSlicer window is the one thing the CLI cannot do, and it
is the ConfigServer's actual reason to exist.

What is kept: the fork builds and the C++ half is verified working. If
live-GUI control turns out to matter, `mcp-on-latest` is there and proven, and
the remaining work is only the Python layer.

`superslicer_fastmcp_server.py`, `run_mcp_server.sh` and `requirements-mcp.txt`
stay in the tree untouched and known broken. They are documented as such here
and in `../todo/open-items.md` rather than deleted, because they are guysoft's
code and still the reference for what the 25 tools were meant to do.

## Alternatives rejected

**Rewrite the existing Python half.** Port to FastMCP 3.x, convert to stdio,
fix requirements, rewire 25 tools to the loopback ConfigServer. Most work of
the three options. Only justified once live-GUI control is a demonstrated need
rather than a hypothetical one.

**Thin stdio MCP server wrapping the CLI.** Roughly 150 lines against current
FastMCP, shelling out to the stock app binary. No C++ fork, no listener, no
upstream divergence. This is the better option if the CLI proves useful and the
friction of invoking it directly becomes the bottleneck. Deferred rather than
rejected outright.
