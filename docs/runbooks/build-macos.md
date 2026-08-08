# Runbook: building on macOS

Status as of 2026-08-08: dependency stage run once. 21 of 22 dependencies
build, OpenVDB does not. Slicer stage not yet attempted. Sections below marked
"measured" record what happened; anything still marked "predicted" has not been
tested. Full account in
`../implementation-logs/2026-08-08-first-build-attempt-macos.md`.

## Host

| | |
|---|---|
| macOS | 26.5, build 25F71 |
| Arch | arm64 |
| Xcode | 26.6, build 17F113 |
| cmake | 4.4.2, Homebrew, arm64 |
| Cores | 18 |
| Free disk | 892Gi on the data volume |
| Python | 3.14.6 |

## Where the repo lives

`~/Developer/SuperSlicerMCP`. Moved out of iCloud on 2026-08-08 with `ditto`,
so the old iCloud copy still exists as a fallback but is now behind. Do not
build in iCloud: the dependency stage alone writes 5.8G into `deps/build`.

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

Measured: that export does its job. CMake 4 removes support for
`cmake_minimum_required(VERSION <3.5)`, and this tree declares two below that
floor, `deps/+OpenCSG/CMakeLists.txt.in:1` at 3.0 and
`deps/+PNG/CMakeLists.txt.patched:14` at 3.0.2. Both built clean under cmake
4.4.2. There is no need to install a 3.x cmake alongside.

## Recommended sequence

Run the dependency stage alone first. It takes the longest and is where breakage
concentrates, so isolating it makes the failure legible.

```bash
cd ~/Developer/SuperSlicerMCP
git checkout mcp-on-latest
./BuildMacOS.sh -d -a > ~/Developer/build-logs/deps-arm64.log 2>&1
./BuildMacOS.sh -s -a > ~/Developer/build-logs/slicer-arm64.log 2>&1
```

Redirect. The dependency log alone ran to 50,795 lines, and the failure is
buried in warning noise that scrolls past.

Add `-t` to the second command to build `test_config_server.cpp` along with the
rest of the test suite.

Measured: the dependency stage takes about six and a half minutes on 18 cores
and writes 5.8G into `deps/build`. Twenty-one of twenty-two dependencies
succeed and drop 115 libraries into `deps/build/destdir/usr/local/lib`. The
twenty-second, OpenVDB, fails. See below. The stage exits 1 and the slicer
stage cannot run until that is resolved.

The slicer stage configures with `-DCMAKE_PREFIX_PATH` pointing at
`deps/build/destdir/usr/local` and `-DSLIC3R_STATIC=1`, so the dependency stage
has to complete before it will work.

## Known obstacles

### OpenVDB fails to compile under Apple Clang 26 (measured, unresolved)

The one dependency that does not build. Eleven translation units, one
diagnostic, three source lines:

```
NodeManager.h:330:31: error: a template argument list is expected after a name
prefixed by the template keyword
[-Wmissing-template-arg-list-after-template-kw]
```

Also at lines 350 and 375. All three write `OpT::template eval(mNodeOp, it)`,
a `template` keyword with no argument list. Apple Clang 26 makes that
diagnostic a default error, so no `-Werror` is involved.

`deps/+OpenVDB/OpenVDB.cmake` pins OpenVDB "8.2 patched" from a prusa3d fork by
commit hash. Upstream fixed the construct well after 8.2.

Proposed fix, not yet applied. Add to `CMAKE_ARGS` in
`deps/+OpenVDB/OpenVDB.cmake`:

```cmake
-DCMAKE_CXX_FLAGS=${DEP_WERRORS_SDK} -Wno-error=missing-template-arg-list-after-template-kw
```

`DEP_WERRORS_SDK` must be repeated.
`cmake/modules/AddCMakeProject.cmake:72-73` expands `${DEP_CMAKE_OPTS}` before
`${P_ARGS_CMAKE_ARGS}`, so a per-project `-DCMAKE_CXX_FLAGS` replaces the global
one instead of appending. Omit it and OpenVDB loses the SDK-availability
guards.

### Deployment target pinned to 10.14 is not the problem (measured)

Hardcoded at lines 264, 267, 393 and 395:

```bash
cmake .. -DCMAKE_OSX_DEPLOYMENT_TARGET="10.14" $BUILD_ARGS
```

This was predicted to be the main source of dependency-stage breakage. It was
not. Twenty-one dependencies, OCCT and wxWidgets among them, compiled against
the macOS 26 SDK with `-mmacosx-version-min=10.14`.

`deps/CMakeLists.txt:121` sets `DEP_WERRORS_SDK` to
`-Werror=partial-availability -Werror=unguarded-availability
-Werror=unguarded-availability-new`, which exists precisely to catch a modern
SDK being used against an old deployment target. None of the three fired.

Leave the target at 10.14. If a later stage does produce availability errors,
the guards above will name them explicitly, and only then is raising the target
worth trying:

```bash
./BuildMacOS.sh -d -a -DCMAKE_OSX_DEPLOYMENT_TARGET=11.0
```

Whatever value gets used, the slicer stage has to match the deps stage or
linking will fail.

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
