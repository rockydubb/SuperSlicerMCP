# MCP and ConfigServer architecture

How an AI assistant ends up able to drive SuperSlicer. Everything below was read
off the code on `mcp-on-latest`, not from the branch documentation, which is
partly stale.

## Two processes

```
AI client (Claude, etc.)
      |
      |  MCP protocol
      v
superslicer_fastmcp_server.py        Python, FastMCP, 25 tools
      |
      |  HTTP on 127.0.0.1:21987
      v
ConfigServer                          C++, Boost.Asio + Beast
      |  compiled into the binary
      v
SuperSlicer GUI application
```

The Python half speaks MCP to the assistant and HTTP to the slicer. The C++ half
is an HTTP server living inside the SuperSlicer process, holding a pointer to
`GUI_App` and reaching into the running application.

Neither half works alone. The Python server has nothing to talk to without a
SuperSlicer built from this branch, and the ConfigServer has no MCP surface
without the Python process.

## C++ side: ConfigServer

Files: `src/slic3r/Utils/ConfigServer.cpp` and `.hpp`, registered in
`src/slic3r/CMakeLists.txt:381-382`.

The class runs a `boost::asio::io_context` on its own `std::thread`, accepting
connections and parsing them as HTTP with Beast. Public surface is small:

```cpp
bool start(uint16_t port = 21987);
void stop();
bool is_running() const;
uint16_t get_port() const;
const std::string& get_instance_id() const;
void set_gui_app(GUI::GUI_App* app);
void register_command_handler(const std::string& command, CommandCallback handler);
```

### HTTP endpoints

Five, accepting GET, POST and PUT:

| Endpoint | Purpose |
|---|---|
| `/api/config` | Read and write configuration values |
| `/api/presets` | Preset listing and retrieval |
| `/api/status` | Application and print state |
| `/api/command` | Generic command dispatch |
| `/api/list_instances` | Enumerate other running instances |

### Command dispatch

`/api/command` routes on a `command` field to eight handlers:
`get_config`, `set_config`, `get_preset`, `list_presets`, `slice`, `export`,
`get_status`, `load_file`. Two more handlers exist on the class but are not
reachable through the command router: `handle_list_config_keys` and
`handle_list_instances`, the latter served by its own endpoint instead.

### Touching the GUI safely

wxWidgets is not thread-safe and the server runs off the main thread, so
mutations are marshalled back with `wxGetApp().CallAfter`. The five app entry
points `ConfigServer.cpp` uses are `wxGetApp().plater`, `.mainframe`,
`.get_tab`, `.preset_bundle` and `.CallAfter`. That short list is why the port
onto a newer base was low risk.

### Multi-instance handling

`start()` will walk up to 10 ports from its base if 21987 is taken
(`ConfigServer.cpp:58-110`), so a second SuperSlicer lands on 21988 and so on.

Each instance writes a JSON descriptor into a registry directory under the system
temp path, `superslicer_instances/<instance_id>.json`, and removes it on
shutdown. `cleanup_stale_instances()` clears descriptors left behind by crashes.
That registry is what `/api/list_instances` and the Python
`discover_instances` tool read.

## Turning it on

Off by default. Three ways to enable it:

```bash
superslicer --enable-config-server
```

The CLI option is declared in `src/libslic3r/PrintConfig.cpp:12019` and parsed in
`src/PrusaSlicer.cpp:225`, which sets `enable_config_server` on the init params.

Or persist it through `AppConfig`, keys `enable_config_server_at_startup` and
`config_server_port`, read at `src/slic3r/GUI/GUI_App.cpp:1888` and `:1896`.

Or use the GUI preferences pane, wired at `src/slic3r/GUI/Preferences.cpp:786-817`.

## Python side: FastMCP server

`superslicer_fastmcp_server.py` exposes 25 MCP tools:

Instance handling: `discover_instances`, `list_instances`, `select_instance`,
`get_current_instance`, `check_connection`.

Configuration: `get_config`, `set_config`, `batch_config`, `search_config`,
`validate_config`, `reset_to_defaults`.

Presets: `list_presets`, `get_preset`, `select_preset`, `save_preset`.

Plate and geometry: `load_file`, `clear_plate`, `arrange_objects`,
`get_object_info`.

Slicing and output: `slice`, `export_gcode`, `export_`, `get_print_statistics`,
`get_status`, `execute_gcode_macro`.

There is a second, older script `mcp_server.py` (416 lines) with no FastMCP tool
decorators. `superslicer_fastmcp_server.py` (31KB) is the one to use.
`run_mcp_server.sh` is the launcher.

Dependencies are pinned in `requirements-mcp.txt`, headed by `fastmcp>=0.1.0` and
`uvicorn[standard]>=0.24.0`. That floor on fastmcp is old enough to be a problem,
see `todo/open-items.md`.

## Security shape

The server binds a local HTTP port with no authentication, no TLS, and a JSON
command surface that can load files, write configuration and trigger exports.
Anything able to reach 21987 can drive the slicer and write to disk through it.
That is acceptable for a loopback development tool on a single-user machine. It
should not be bound to a routable interface, and the FastMCP layer should not be
put behind a network listener without adding authentication first.

`FASTMCP_README.md` documents a `uvicorn --host 0.0.0.0` invocation. Do not use
that form.
