# First successful build, and the ConfigServer answering over HTTP

Date: 2026-08-08. Branch `mcp-on-latest`.

`mcp-on-latest` compiles and the MCP half works. Dependency stage exit 0, slicer
stage exit 0, a 90MB arm64 binary, and all five ConfigServer endpoints returning
200 with real data.

One security finding came out of the smoke test, described at the end. It is not
introduced by the port, but it contradicts what `CLAUDE.md` claims.

## The OpenVDB fix

`deps/+OpenVDB/OpenVDB.cmake` now demotes the one diagnostic that stopped the
build:

```cmake
set(_openvdb_extra_args "")
if (APPLE)
    set(_openvdb_extra_args
        "-DCMAKE_CXX_FLAGS=${DEP_WERRORS_SDK} -Wno-error=missing-template-arg-list-after-template-kw")
endif ()
```

Expanded into `CMAKE_ARGS` as `${_openvdb_extra_args}`, which vanishes on
non-Apple platforms rather than clobbering Linux flags with an empty string.

`DEP_WERRORS_SDK` is repeated deliberately.
`cmake/modules/AddCMakeProject.cmake:72-73` expands `${DEP_CMAKE_OPTS}` before a
project's own `CMAKE_ARGS`, so this `-DCMAKE_CXX_FLAGS` replaces the global one
instead of appending. Verified in the generated
`builds/OpenVDB/.../openvdb_static.dir/flags.make`, which came out as:

```
-Werror=partial-availability -Werror=unguarded-availability
-Werror=unguarded-availability-new
-Wno-error=missing-template-arg-list-after-template-kw
-O3 -DNDEBUG -std=c++14 -arch arm64 -mmacosx-version-min=10.14 -fPIC
```

Both the SDK guards and the new suppression. Nothing lost.

`-Wno-error=` rather than `-Wno-`, so the diagnostic still prints. It fired 30
times as a warning in the successful run, which is the point: if the pin ever
moves off OpenVDB 8.2, the noise is still there to notice.

### Making it take effect

ExternalProject caches its configure step. Changing `CMAKE_ARGS` alone does not
force a reconfigure, and `builds/OpenVDB/CMakeCache.txt` still held the old
`CMAKE_CXX_FLAGS`. Removing two things was enough:

```bash
rm -f deps/build/dep_OpenVDB-prefix/src/dep_OpenVDB-stamp/dep_OpenVDB-configure
rm -rf deps/build/builds/OpenVDB
```

Download and extract stamps left alone, so the tarball was not refetched, and
the other 21 dependencies were untouched.

## Build results

Dependency stage, second run:

```
EXIT=0
```

1,593 lines. Zero errors. All 22 dependencies stamped, OpenVDB among them.

Slicer stage:

```bash
./BuildMacOS.sh -s -a
```

```
[100%] Linking CXX executable ../bin/superslicer
[100%] Built target Slic3r
EXIT=0
```

36,566 lines, zero errors. The MCP C++ code compiled with one warning:

```
src/slic3r/Utils/ConfigServer.cpp:653:25: warning: unused variable 'mainframe'
[-Wunused-variable]
```

Cosmetic. Left alone.

Output:

```
build/bin/superslicer                    93,933,192 bytes, Mach-O 64-bit executable arm64
build/bin/SuperSlicer-gcodeviewer        symlink to superslicer
```

Note the path. Earlier notes said `build/src/superslicer`. The link line puts it
at `build/bin/superslicer`.

`--enable-config-server` is present in `--help`, so the CLI option registered.

No `.app` bundle. `-s` produces a raw executable; the bundle is assembled by
`src/platform/osx/BuildMacOSImage.sh.in`, which only runs under `-i`.

## First launch failed, for an unrelated reason

```
Internal error: boost::filesystem::copy: No such file or directory [system:2]:
"~/Library/Application Support/SuperSlicer/snapshots",
"~/Library/Application Support/SuperSlicer/SuperSlicer_2.7.62.0-beta2/snapshots"
```

SuperSlicer migrates an existing config directory into a versioned subfolder on
first run of a new version, and the `snapshots` source directory was not there.
Nothing to do with the port.

The app did not exit on the error. It queued the message through `wxLogGui` and
blocked in `wxEntryCleanup` showing a modal alert, so from the outside it looked
like a hung process with no window. A `sample` of the stuck process is what made
this legible:

```
wxEntryCleanup() -> wxLog::SetActiveTarget -> wxLogGui::Flush
  -> wxMessageBox -> wxMessageDialog::ShowModal -> -[NSAlert runModal]
```

Worth remembering. A SuperSlicer startup failure presents as a hang, not a
crash, and the reason is sitting in a dialog the terminal never mentions.

### Resolved by isolating the data directory

```bash
./build/bin/superslicer --datadir ~/Developer/superslicer-dev-data \
                        --enable-config-server
```

Better than creating the missing `snapshots` folder. This build is an unproven
beta and the default path is the same directory the production SuperSlicer
install uses, holding real printer profiles. Keep the dev build out of it.

## ConfigServer smoke test

Listening within 30 seconds of launch:

```
superslic 71233 rockydubb 10u IPv4 TCP *:21987 (LISTEN)
```

All endpoints, all 200:

| Endpoint | Bytes | Content |
|---|---|---|
| `/api/status` | 156 | `{"app_version": "2.7.62-beta2", "instance_id": "71233_21987", "port": 21987, "project_name": "", "has_model": false, "object_count": 0, "process_id": 71233}` |
| `/api/list_instances` | 109 | one instance, port 21987, pid 71233, start_time 1786194661 |
| `/api/presets` | 15 | `{"presets": []}`, empty because the dev datadir is fresh |
| `/api/config` | 194,192 | full key inventory with type, tooltip and label per key |

`/api/config` returning 194KB of annotated configuration keys is the thing worth
noting. That is the surface an assistant actually drives, and it is intact after
the port.

## Security finding: the server binds to every interface

`ConfigServer.cpp:64`:

```cpp
m_acceptor = std::make_unique<tcp::acceptor>(
    *m_io_context, tcp::endpoint(tcp::v4(), current_port));
```

`tcp::v4()` as an endpoint address is `INADDR_ANY`, so this is `0.0.0.0`, not
`127.0.0.1`. Confirmed twice: `lsof` reports `*:21987` rather than
`127.0.0.1:21987`, and a request to `http://0.0.0.0:21987/api/status` returned
200.

`CLAUDE.md` states the server is loopback only. That is an assumption about
intent, not a description of the code. In practice the server is reachable from
any host on the same network, it has no authentication and no TLS, and it can
write configuration and load files.

One-line fix, not applied:

```cpp
tcp::endpoint(boost::asio::ip::make_address("127.0.0.1"), current_port)
```

Until that lands, treat "enable the config server" as "open an unauthenticated
write-capable API to the LAN" and act accordingly on untrusted networks.

## Not done

- Python half untouched. `requirements-mcp.txt` still floors `fastmcp>=0.1.0`,
  see `docs/todo/open-items.md`.
- No `.app` bundle built.
- Bind address not changed.
- `mainframe` unused-variable warning not cleaned up.
