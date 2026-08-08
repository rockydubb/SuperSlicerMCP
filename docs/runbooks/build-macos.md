# Runbook: building on macOS

Status as of 2026-08-08: not yet performed. Everything here comes from reading
`BuildMacOS.sh` and checking the host. Treat the blockers as predictions, and
update this file with what actually happens on the first real run.

## Host at time of writing

| | |
|---|---|
| macOS | 26.5, build 25F71 |
| Arch | arm64 |
| Xcode | 26.6, build 17F113 |
| cmake | not installed |
| Cores | 18 |
| Free disk | 892Gi on the data volume |
| Python | 3.14.6 |

## Script flags

`BuildMacOS.sh` takes:

| Flag | Effect |
|---|---|
| `-h` | usage |
| `-w` | wipe build directories first |
| `-d` | build dependencies |
| `-r` | delete dependency build files afterwards to reclaim disk |
| `-a` | target arm64 |
| `-x` | target x86_64 |
| `-b` | include debug symbols |
| `-c` | generate an XCode project |
| `-s` | build SuperSlicer itself |
| `-t` | build tests, use with `-s` |
| `-i` | produce a DMG |
| `-v` | replace the `UNKNOWN` version string with today's date |

## Prerequisites

```bash
brew install cmake
```

The script checks for cmake at line 70 and aborts at line 73 if it is missing.
It also exports `CMAKE_POLICY_VERSION_MINIMUM=3.5` at line 16, which is how it
copes with old dependency CMake files under a modern cmake.

## Recommended sequence

Run the dependency stage alone first. It takes the longest and is where breakage
concentrates, so isolating it makes the failure legible.

```bash
cd <repo root>
git checkout mcp-on-latest
./BuildMacOS.sh -d -a          # dependencies, arm64
./BuildMacOS.sh -s -a          # then SuperSlicer
```

Add `-t` to the second command to build `test_config_server.cpp` along with the
rest of the test suite.

The slicer stage configures with `-DCMAKE_PREFIX_PATH` pointing at
`deps/build/destdir/usr/local` and `-DSLIC3R_STATIC=1`, so the dependency stage
has to complete before it will work.

## Known obstacles

### Deployment target is pinned to 10.14

Hardcoded at lines 264, 267, 393 and 395:

```bash
cmake .. -DCMAKE_OSX_DEPLOYMENT_TARGET="10.14" $BUILD_ARGS
```

The host SDK is macOS 26. Targeting 10.14 against it spans twelve major versions,
and the dependency stack is where that tends to surface as missing or deprecated
symbols. If deps fail on symbol errors, raise the target rather than fighting it:

```bash
./BuildMacOS.sh -d -a -DCMAKE_OSX_DEPLOYMENT_TARGET=11.0
```

If the flag does not pass through cleanly, edit the four call sites directly.
Whatever value gets used, the slicer stage has to match the deps stage or linking
will fail.

### Script was tuned for Xcode 14 and 15

Lines 160 to 167 `ls` into `/Applications/Xcode_14.3.1.app` and
`Xcode_15.2.0.app`, which are GitHub CI runner paths. The `ls` calls themselves
are harmless diagnostics that will print errors and continue. The signal matters
more than the noise: nobody has run this against Xcode 26.

### Dependency rot

guysoft's three most recent commits on `feature/config_server`, all dated
2026-03-19, are dependency build fixes: MPFR automake version mismatch, static
libpng resolution, and a GCC 15 `-Wtemplate-body` suppression for bundled CGAL
headers. He was fighting this stack five months ago on Linux. Expect the macOS
and Clang equivalents. Those commits are not on `mcp-on-latest` because they are
GCC-specific, but they are available on `upstream/feature/config_server` if a
pattern in them turns out to apply.

### Repository location

The repo currently sits in iCloud Drive, 349M of `.git` and 501M total. A full
dependency stack plus the slicer produces a large number of object files, and
iCloud will attempt to sync each one as it is written. This is slow and can
corrupt a build in progress. Move it before building:

```bash
mkdir -p ~/Developer
mv "<current iCloud path>" ~/Developer/SuperSlicerMCP
```

Space is not the constraint, location is.

## Verifying the MCP half after a successful build

```bash
./build/bin/superslicer --enable-config-server
```

Then from another shell:

```bash
lsof -i :21987                                  # is it listening
curl -s http://127.0.0.1:21987/api/status       # does it answer
```

If 21987 is occupied the server walks up to ten ports, so check 21988 onward
before concluding it failed to start. Running instances also register themselves
as JSON files under `superslicer_instances/` in the system temp directory, which
is a second way to find the live port.

Once the C++ half answers:

```bash
pip install -r requirements-mcp.txt
./run_mcp_server.sh
```

Expect friction here. `requirements-mcp.txt` pins `fastmcp>=0.1.0`, a floor old
enough that a fresh install pulls a much later version with a changed API. See
`docs/todo/open-items.md`.

## Do not follow MCP_INTEGRATION_STATUS.md

That file, inherited from guysoft's branch, says the ConfigServer "is not yet
integrated into the SuperSlicer build" and instructs you to apply
`integrate_configserver.patch` from `/home/guy/tmp/SuperSlicer`. The patch is not
in the tree and the integration is already committed. The path is guysoft's own
machine. Use `FASTMCP_README.md` instead.
