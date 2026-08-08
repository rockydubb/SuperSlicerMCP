# Runbook: building on macOS

Status as of 2026-08-08: builds clean and runs. Both stages exit 0, the binary
launches, and all five ConfigServer endpoints answer. Sections marked
"measured" record what happened.

Full account across two logs:
`../implementation-logs/2026-08-08-first-build-attempt-macos.md` for the failed
first run, and
`../implementation-logs/2026-08-08-first-successful-build-and-configserver-smoke-test.md`
for the fix and the working result.

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

### OpenVDB under Apple Clang 26 (measured, fixed 2026-08-08)

Was the one dependency that would not build. Eleven translation units, one
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

Fixed in `deps/+OpenVDB/OpenVDB.cmake`, which now demotes the diagnostic on
Apple only:

```cmake
set(_openvdb_extra_args "")
if (APPLE)
    set(_openvdb_extra_args
        "-DCMAKE_CXX_FLAGS=${DEP_WERRORS_SDK} -Wno-error=missing-template-arg-list-after-template-kw")
endif ()
```

`DEP_WERRORS_SDK` must be repeated.
`cmake/modules/AddCMakeProject.cmake:72-73` expands `${DEP_CMAKE_OPTS}` before
`${P_ARGS_CMAKE_ARGS}`, so a per-project `-DCMAKE_CXX_FLAGS` replaces the global
one instead of appending. Omit it and OpenVDB loses the SDK-availability
guards.

If you ever change these flags, ExternalProject will not reconfigure on its
own. Clear the configure stamp and the build directory, keeping the downloaded
tarball:

```bash
rm -f deps/build/dep_OpenVDB-prefix/src/dep_OpenVDB-stamp/dep_OpenVDB-configure
rm -rf deps/build/builds/OpenVDB
```

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

### A failed startup looks like a hang, not a crash (measured)

The first launch appeared to be a stuck process: alive, no window, empty log,
nothing listening. It had actually failed during init, queued the message
through `wxLogGui`, and blocked in `wxEntryCleanup` showing a modal alert that
never reached the terminal.

When that happens, sample the process rather than guessing:

```bash
sample $(pgrep -f build/bin/superslicer) 3 -file /tmp/ss-sample.txt
```

A stack ending in `wxLogGui::Flush -> wxMessageBox -> -[NSAlert runModal]` means
the reason is in a dialog. Read it without clicking:

```bash
osascript -e 'tell application "System Events" to tell (first process whose \
  unix id is <PID>) to get value of every static text of every window'
```

### Use a separate data directory (measured)

The actual first-run failure was:

```
Internal error: boost::filesystem::copy: No such file or directory [system:2]:
".../SuperSlicer/snapshots", ".../SuperSlicer/SuperSlicer_2.7.62.0-beta2/snapshots"
```

SuperSlicer migrates an existing config directory into a versioned subfolder
when it sees a new version, and `snapshots` was not there to copy.

Do not fix this by creating the folder. The default path is the same
`~/Library/Application Support/SuperSlicer` your production install uses, and
this build is an unproven beta that will migrate real printer profiles. Give it
its own directory:

```bash
--datadir ~/Developer/superslicer-dev-data
```

### Dependency rot

guysoft's three most recent commits on `feature/config_server`, all dated
2026-03-19, are dependency build fixes: MPFR automake version mismatch, static
libpng resolution, and a GCC 15 `-Wtemplate-body` suppression for bundled CGAL
headers. He was fighting this stack five months ago on Linux.

The OpenVDB fix above turned out to be the macOS equivalent, and the same shape:
demote a compiler diagnostic on a vendored dependency rather than patch it. Only
one was needed. The rest of the stack built unmodified.

### Repository location

Resolved 2026-08-08. The repo was in iCloud Drive and is now at
`~/Developer/SuperSlicerMCP`. Keep it there. The dependency stage alone writes
5.8G into `deps/build`, and iCloud tries to sync every object file as it lands.
Space was never the constraint, location was.

## Verifying the MCP half (measured 2026-08-08, all passing)

```bash
./build/bin/superslicer --datadir ~/Developer/superslicer-dev-data \
                        --enable-config-server
```

Note the path: `build/bin/superslicer`, not `build/src/`. `-s` produces a raw
executable and no `.app` bundle. The bundle is assembled by
`src/platform/osx/BuildMacOSImage.sh.in`, which only runs under `-i`.

Then from another shell:

```bash
lsof -nP -iTCP:21987 -sTCP:LISTEN                # is it listening
curl -s http://127.0.0.1:21987/api/status        # does it answer
```

Takes under 30 seconds from launch to listening. Measured responses, all 200:

| Endpoint | Bytes | Notes |
|---|---|---|
| `/api/status` | 156 | version, instance_id, port, project, model flags, pid |
| `/api/list_instances` | 109 | one entry per running instance |
| `/api/presets` | 15 | empty on a fresh datadir |
| `/api/config` | 194,192 | every config key with type, tooltip and label |
| `/api/command` | n/a | eight commands, not yet exercised |

If 21987 is occupied the server walks up to ten ports, so check 21988 onward
before concluding it failed to start. Running instances also register themselves
as JSON files under `superslicer_instances/` in the system temp directory, which
is a second way to find the live port.

### The server is not loopback only

`ConfigServer.cpp:64` builds its acceptor as
`tcp::endpoint(tcp::v4(), current_port)`. As an endpoint address, `tcp::v4()` is
`INADDR_ANY`, so the bind is `0.0.0.0`. `lsof` confirms it, reporting `*:21987`
rather than `127.0.0.1:21987`, and a request to `http://0.0.0.0:21987/api/status`
returns 200.

There is no authentication and no TLS, and the API can write configuration and
load files. Enabling the config server on an untrusted network exposes all of
that to every host that can reach the machine.

One-line fix, not yet applied:

```cpp
tcp::endpoint(boost::asio::ip::make_address("127.0.0.1"), current_port)
```

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
