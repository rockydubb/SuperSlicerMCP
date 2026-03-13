# SuperSlicer MCP Integration Plan

## Goal
Create an MCP server that can communicate with **running SuperSlicer instances** to read and modify configuration values in real-time, allowing changes to be applied to the current 3MF project being worked on.

## Analysis of SuperSlicer Architecture

### 1. **Current IPC/Communication Capabilities**

#### A. Instance Management (`src/slic3r/GUI/InstanceCheck.cpp`)
- SuperSlicer already has single-instance checking
- Uses platform-specific IPC mechanisms:
  - **Linux**: Unix domain sockets
  - **Windows**: Named pipes  
  - **macOS**: Distributed notifications
- Can detect and communicate with running instances
- Currently used to pass file paths to open

#### B. AngelScript Integration (`src/slic3r/GUI/ScriptExecutor.cpp`)
- SuperSlicer has embedded AngelScript engine
- Used for configuration scripting
- Can access and modify configuration values
- Executes in the GUI thread context

#### C. TCPConsole (`src/slic3r/Utils/TCPConsole.cpp`)
- TCP client for sending commands to printers
- Not suitable for our needs (client, not server)

### 2. **Configuration System Architecture**

#### Key Classes:
- `DynamicPrintConfig` - Runtime configuration storage
- `Tab` - GUI tab management (Print, Filament, Printer settings)
- `Plater` - Main 3D view and object manipulation
- `GUI_App` - Main application controller
- `ConfigOptionDef` - Configuration option definitions

#### Configuration Flow:
```
GUI (Tab) -> DynamicPrintConfig -> Apply to Model -> Slice -> GCode
```

## Proposed MCP Integration Approaches

### Approach 1: **Socket-Based Command Server** (Recommended)

#### Implementation:
1. **Add TCP/Unix Socket Server to SuperSlicer**
   - Location: `src/slic3r/Utils/ConfigServer.cpp`
   - Listen on configurable port (default: 35532)
   - Protocol: JSON-RPC or simple text commands
   - Runs in separate thread to avoid blocking GUI

2. **Command Set**:
   ```json
   // Get current configuration
   {"cmd": "get_config", "preset_type": "print", "key": "layer_height"}
   
   // Set configuration value
   {"cmd": "set_config", "preset_type": "print", "key": "layer_height", "value": "0.2"}
   
   // List presets
   {"cmd": "list_presets", "preset_type": "print"}
   
   // Get current project info
   {"cmd": "get_project_info"}
   
   // Trigger reslice
   {"cmd": "reslice"}
   ```

3. **Integration Points**:
   - Hook into `GUI_App::init()` to start server
   - Access `wxGetApp().plater()` for current project
   - Use `Tab::load_config()` and `Tab::update_config()` for config changes
   - Emit events through `wxGetApp().plater()->on_config_change()`

4. **Code Locations to Modify**:
   ```cpp
   // src/slic3r/GUI/GUI_App.cpp - Add server initialization
   void GUI_App::init() {
       // ... existing code ...
       if (app_config->get("enable_config_server") == "1") {
           m_config_server = std::make_unique<ConfigServer>(35532);
           m_config_server->start();
       }
   }
   
   // src/slic3r/Utils/ConfigServer.cpp - New file
   class ConfigServer {
       void handle_command(const json& cmd) {
           if (cmd["cmd"] == "set_config") {
               auto* tab = wxGetApp().get_tab(cmd["preset_type"]);
               tab->update_config_value(cmd["key"], cmd["value"]);
           }
       }
   };
   ```

### Approach 2: **Extended Instance Check Protocol**

#### Implementation:
1. **Extend existing InstanceCheck mechanism**
   - Currently in `src/slic3r/GUI/InstanceCheck.cpp`
   - Add command protocol beyond just file paths
   - Reuse existing platform-specific IPC

2. **Advantages**:
   - Minimal new code
   - Platform-native IPC
   - Already has instance discovery

3. **Disadvantages**:
   - Limited to single instance
   - More complex protocol design
   - Platform-specific implementations

### Approach 3: **AngelScript Bridge**

#### Implementation:
1. **Expose AngelScript engine via TCP/HTTP**
   - Create script execution endpoint
   - Scripts can manipulate configuration

2. **Advantages**:
   - Leverages existing scripting system
   - Very flexible

3. **Disadvantages**:
   - Security concerns (arbitrary script execution)
   - More complex MCP client implementation
   - Performance overhead

## Detailed Implementation Plan (Approach 1)

### Phase 1: Core Server Implementation

#### Files to Create:
```
src/slic3r/Utils/ConfigServer.hpp
src/slic3r/Utils/ConfigServer.cpp
```

#### ConfigServer.hpp:
```cpp
#ifndef slic3r_ConfigServer_hpp_
#define slic3r_ConfigServer_hpp_

#include <thread>
#include <atomic>
#include <boost/asio.hpp>
#include "libslic3r/Config.hpp"

namespace Slic3r {
namespace GUI {

class ConfigServer {
public:
    ConfigServer(int port = 35532);
    ~ConfigServer();
    
    void start();
    void stop();
    bool is_running() const { return m_running; }
    
private:
    void accept_loop();
    void handle_client(std::shared_ptr<boost::asio::ip::tcp::socket> socket);
    std::string process_command(const std::string& cmd);
    
    int m_port;
    std::atomic<bool> m_running{false};
    std::unique_ptr<std::thread> m_thread;
    std::unique_ptr<boost::asio::io_context> m_io_context;
    std::unique_ptr<boost::asio::ip::tcp::acceptor> m_acceptor;
};

} // namespace GUI
} // namespace Slic3r

#endif
```

### Phase 2: Command Processing

#### Commands to Implement:
1. **Configuration Commands**
   - `get_config`: Read configuration value
   - `set_config`: Set configuration value
   - `get_all_config`: Get all config for a preset type
   - `list_presets`: List available presets
   - `load_preset`: Load a preset

2. **Project Commands**
   - `get_project_info`: Current 3MF project details
   - `get_objects`: List of objects in scene
   - `get_object_config`: Per-object configuration

3. **Action Commands**
   - `reslice`: Trigger slicing
   - `export_gcode`: Export G-code
   - `save_project`: Save current project

### Phase 3: MCP Server Wrapper

#### Python MCP Server (`superslicer-mcp-server.py`):
```python
#!/usr/bin/env python3
from fastmcp import FastMCP
import socket
import json

mcp = FastMCP("SuperSlicer Live")

class SuperSlicerClient:
    def __init__(self, host='localhost', port=35532):
        self.host = host
        self.port = port
    
    def send_command(self, cmd):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.host, self.port))
            s.sendall(json.dumps(cmd).encode() + b'\n')
            response = s.recv(4096)
            return json.loads(response)

client = SuperSlicerClient()

@mcp.tool()
def get_config(preset_type: str, key: str):
    """Get configuration value from running SuperSlicer"""
    return client.send_command({
        "cmd": "get_config",
        "preset_type": preset_type,
        "key": key
    })

@mcp.tool()
def set_config(preset_type: str, key: str, value: str):
    """Set configuration value in running SuperSlicer"""
    return client.send_command({
        "cmd": "set_config",
        "preset_type": preset_type,
        "key": key,
        "value": value
    })

if __name__ == "__main__":
    mcp.run()
```

## Build Integration

### CMakeLists.txt Modification:
```cmake
# In src/slic3r/CMakeLists.txt
set(SLIC3R_GUI_SOURCES
    # ... existing sources ...
    Utils/ConfigServer.cpp
    Utils/ConfigServer.hpp
)

# Add Boost.Asio if not already included
find_package(Boost REQUIRED COMPONENTS system thread)
```

### Configuration Options:
Add to `src/libslic3r/PrintConfig.cpp`:
```cpp
def = this->add("enable_config_server", coBool);
def->label = L("Enable configuration server");
def->tooltip = L("Enable TCP server for external configuration control");
def->mode = comExpert;
def->set_default_value(new ConfigOptionBool(false));

def = this->add("config_server_port", coInt);
def->label = L("Configuration server port");
def->tooltip = L("TCP port for configuration server");
def->mode = comExpert;
def->set_default_value(new ConfigOptionInt(35532));
```

## Testing Strategy

### 1. Unit Tests
- Test command parsing
- Test configuration changes
- Test thread safety

### 2. Integration Tests
- Start SuperSlicer with server enabled
- Connect MCP client
- Verify configuration changes reflect in GUI
- Verify slicing updates with new settings

### 3. End-to-End Test
```bash
# Start SuperSlicer
./superslicer --enable-config-server

# Run MCP server
python superslicer-mcp-server.py

# Test with client
echo '{"cmd": "get_config", "preset_type": "print", "key": "layer_height"}' | nc localhost 35532
```

## Security Considerations

1. **Authentication**: Add token-based auth for production
2. **Validation**: Validate all configuration values before applying
3. **Sandboxing**: Limit commands to configuration only
4. **Local Only**: Default to localhost binding
5. **Rate Limiting**: Prevent DoS attacks

## Performance Considerations

1. **Threading**: Server runs in separate thread
2. **Event Queue**: Commands queued and processed in GUI thread
3. **Debouncing**: Batch rapid configuration changes
4. **Caching**: Cache frequently accessed values

## Alternative: D-Bus Integration (Linux)

For Linux systems, consider D-Bus as an alternative:
```cpp
// Use existing D-Bus support
class ConfigDBusService : public DBusInterface {
    void SetConfig(const std::string& preset_type, 
                   const std::string& key, 
                   const std::string& value);
    std::string GetConfig(const std::string& preset_type, 
                         const std::string& key);
};
```

## Timeline

1. **Week 1**: Implement basic TCP server
2. **Week 2**: Add command processing
3. **Week 3**: Create MCP wrapper
4. **Week 4**: Testing and refinement

## Next Steps

1. Create proof-of-concept TCP server
2. Test with simple get/set commands
3. Integrate with Tab system
4. Build MCP wrapper
5. Test with real configuration changes

## Resources

- SuperSlicer source: `/home/guy/tmp/SuperSlicer/`
- Config system: `src/libslic3r/Config.hpp`
- GUI integration: `src/slic3r/GUI/Tab.cpp`
- Instance check: `src/slic3r/GUI/InstanceCheck.cpp`