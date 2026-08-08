# First build attempt on macOS: dependency stage

Date: 2026-08-08. Branch `mcp-on-latest` at `dbef7d6ae`.

Result: dependency stage fails. 21 of 22 dependencies build. OpenVDB does not.
Exit code 1. The failure is one diagnostic repeated across eleven translation
units, and it has nothing to do with the MCP port.

## What was done first

Three prerequisites, in order.

**Committed the docs tree.** `CLAUDE.md` and `docs/` were untracked, so any
clone or worktree checkout would have arrived without them. Committed as
`dbef7d6ae` and pushed to `origin/mcp-on-latest`.

While staging, `docs/runbooks/build-macos.md` silently refused to be added. The
inherited `.gitignore` carries a bare `build*` rule at line 17, which git matches
against every path component at any depth, not just top-level build directories.
Added a `!docs/**` exception, placed above the `.DS_Store` rule so that rule
still wins inside `docs/`.

**Installed cmake.** Homebrew, version 4.4.2, arm64.

CMake 4 removes support for `cmake_minimum_required(VERSION <3.5)`, and this
tree declares two: `deps/+OpenCSG/CMakeLists.txt.in:1` at 3.0 and
`deps/+PNG/CMakeLists.txt.patched:14` at 3.0.2. This turned out to be a
non-problem. `BuildMacOS.sh:16` already exports
`CMAKE_POLICY_VERSION_MINIMUM=3.5`, which is the escape hatch CMake 4 provides
for exactly this. Both dependencies built without complaint. No need to install
cmake 3.x.

**Moved the repo out of iCloud.** It was at
`~/Library/Mobile Documents/com~apple~CloudDocs/Software Development/08-SuperSlicerMCP/00-main`,
503M. Copied with `ditto` rather than moved, so the iCloud copy survives as a
fallback until a build proves out. New working location:

```
~/Developer/SuperSlicerMCP
```

Verified after copying: `pwd -P` outside iCloud, branch `mcp-on-latest`, clean
tree, HEAD matching, `git fsck` clean apart from expected dangling blobs, both
remotes intact with `upstream` push still DISABLED.

The dependency stage wrote 5.8G into `deps/build`. Running that through the
iCloud file provider would have been the wrong kind of interesting.

## The run

```bash
cd ~/Developer/SuperSlicerMCP
./BuildMacOS.sh -d -a > ~/Developer/build-logs/deps-arm64.log 2>&1
```

Dependency stage only, no slicer build chained to it, so the failure would be
readable.

`deps/build` created 08:27:36, log last written 08:34:15. Roughly six minutes
forty on 18 cores. Log is 50,795 lines.

## What succeeded

Twenty-one dependencies reached their install stamp:

Blosc, Boost, Catch2, Cereal, CGAL, EXPAT, GLEW, GMP, heatshrink, JPEG,
LibBGCode, MPFR, NanoSVG, NLopt, OCCT, OpenCSG, OpenEXR, PNG, Qhull, TBB,
wxWidgets.

115 libraries landed in `deps/build/destdir/usr/local/lib`.

## What failed

OpenVDB. Eleven translation units, one diagnostic, three source lines.

```
NodeManager.h:330:31: error: a template argument list is expected after a name
prefixed by the template keyword
[-Wmissing-template-arg-list-after-template-kw]
```

Same error at lines 350 and 375. All three are the same construct:

```cpp
OpT::template eval(mNodeOp, it);
```

A `template` keyword with no argument list after it. Older Clang accepted this.
Apple Clang 26 classifies `-Wmissing-template-arg-list-after-template-kw` as a
default error, so it stops the build with no `-Werror` involved.

The compile flags confirm there is no blanket `-Werror`:

```
CXX_FLAGS = -Werror=partial-availability -Werror=unguarded-availability
            -Werror=unguarded-availability-new -O3 -DNDEBUG -std=c++14
            -arch arm64 -mmacosx-version-min=10.14 -fPIC
```

Those three `-Werror=` entries are SDK-availability guards set at
`deps/CMakeLists.txt:121` as `DEP_WERRORS_SDK`. They are deliberate and none of
them fired.

The version is old and pinned. `deps/+OpenVDB/OpenVDB.cmake` fetches OpenVDB
"8.2 patched" from a prusa3d fork by commit hash
`a68fd58d0e2b85f01adeb8b13d7555183ab10aa5`. The upstream fix for this construct
landed in OpenVDB well after 8.2.

## The 10.14 prediction was wrong

`docs/runbooks/build-macos.md` named the hardcoded
`CMAKE_OSX_DEPLOYMENT_TARGET=10.14` as the most likely source of
dependency-stage failure. It was not. Twenty-one dependencies, including OCCT
and wxWidgets, built against the macOS 26 SDK with
`-mmacosx-version-min=10.14`, and the SDK-availability guards that exist
specifically to catch that mismatch never fired. Leave the target alone.

## Proposed fix

Suppress the one diagnostic for OpenVDB only. This is the same shape as
guysoft's own CGAL fix on `feature/config_server`, which suppressed a GCC 15
`-Wtemplate-body` diagnostic in bundled headers rather than patching them.

In `deps/+OpenVDB/OpenVDB.cmake`, add to `CMAKE_ARGS`:

```cmake
-DCMAKE_CXX_FLAGS=${DEP_WERRORS_SDK} -Wno-error=missing-template-arg-list-after-template-kw
```

`DEP_WERRORS_SDK` has to be repeated. `cmake/modules/AddCMakeProject.cmake:72-73`
expands `${DEP_CMAKE_OPTS}` before `${P_ARGS_CMAKE_ARGS}`, so a per-project
`-DCMAKE_CXX_FLAGS` replaces the global one rather than appending to it. Drop it
and OpenVDB loses its SDK-availability guards.

`-Wno-error=` rather than `-Wno-`, so the diagnostic still prints and stays
visible if the pinned version ever moves.

Two alternatives, both worse. Bumping OpenVDB past 8.2 means leaving the prusa3d
fork and re-testing every downstream consumer. Patching `NodeManager.h` in place
means carrying a patch against a URL-fetched tarball.

## Not yet done

- Fix not applied. Reporting first, as instructed.
- Slicer stage `./BuildMacOS.sh -s -a` not attempted. It needs the dependency
  stage complete.
- Python half untouched. The `fastmcp>=0.1.0` floor in `requirements-mcp.txt` is
  still unresolved, see `docs/todo/open-items.md`.

## Note on repository location

`~/Developer/SuperSlicerMCP` is the working copy from here on. The iCloud copy
at `08-SuperSlicerMCP/00-main` is now behind and should be treated as dead once
a build succeeds.
