# SuperSlicer MCP Integration

This document describes the Model Context Protocol (MCP) integration for SuperSlicer, which enables real-time configuration control and automation of SuperSlicer instances.

## Overview

The MCP integration consists of two components:

1. **ConfigServer** (C++): An embedded TCP server running inside SuperSlicer that exposes configuration and control APIs
2. **MCP Server** (Python): An MCP protocol server that bridges MCP clients to SuperSlicer's ConfigServer

## Architecture

```
MCP Client (Claude, etc.)
    ↓ (MCP Protocol)
Python MCP Server (mcp_server.py)
    ↓ (TCP/JSON)
ConfigServer (C++ in SuperSlicer)
    ↓ (Direct API calls)
SuperSlicer Core (Config, Presets, Plater, etc.)
```

## Features

### Configuration Management
- **Read configuration values**: Get any configuration parameter value
- **Write configuration values**: Modify configuration in real-time
- **Batch updates**: Set multiple configuration values at once
- **Preset management**: List, query, and switch between presets

### Project Control
- **Load models**: Import 3D files (STL, OBJ, 3MF, etc.)
- **Slicing control**: Trigger slicing operations
- **Export G-code**: Export sliced models to G-code files
- **Status monitoring**: Query application state and loaded models

## Building SuperSlicer with MCP Support

### Prerequisites
- CMake 3.13+
- C++17 compiler
- Boost libraries (including Boost.Asio)
- wxWidgets
- Python 3.8+ (for MCP server)

### Build Steps

1. Add ConfigServer files to the build:
   ```bash
   # Edit src/slic3r/CMakeLists.txt and add:
   # Utils/ConfigServer.cpp
   # Utils/ConfigServer.hpp
   ```

2. Build SuperSlicer:
   ```bash
   cd SuperSlicer
   mkdir build
   cd build
   cmake .. -DSLIC3R_STATIC=1
   make -j$(nproc)
   ```

3. Enable ConfigServer in SuperSlicer (add to GUI initialization):
   ```cpp
   // In GUI_App.cpp, add to initialization:
   #include "Utils/ConfigServer.hpp"
   
   // In GUI_App::OnInit():
   if (app_config->get("enable_config_server") == "1") {
       m_config_server = std::make_unique<ConfigServer>();
       m_config_server->set_gui_app(this);
       m_config_server->start(21987); // Default port
   }
   ```

## Installing the MCP Server

1. Install Python dependencies:
   ```bash
   pip install mcp
   ```

2. Make the MCP server executable:
   ```bash
   chmod +x mcp_server.py
   ```

## Usage

### Starting SuperSlicer with ConfigServer

1. Launch SuperSlicer with the config server enabled:
   ```bash
   ./superslicer --enable-config-server
   ```

   Or add to configuration file:
   ```ini
   enable_config_server = 1
   config_server_port = 21987
   ```

### Running the MCP Server

```bash
python mcp_server.py --superslicer-port 21987
```

### Available MCP Tools

#### Configuration Tools

- **get_config(key)**: Get a configuration value
  ```python
  get_config("layer_height")  # Returns: "0.2"
  ```

- **set_config(key, value)**: Set a configuration value
  ```python
  set_config("layer_height", "0.15")
  ```

- **batch_config(configs)**: Set multiple values at once
  ```python
  batch_config('{"layer_height": "0.2", "infill_density": "20"}')
  ```

#### Preset Tools

- **list_presets()**: List all available presets
- **get_preset(type)**: Get current preset info (type: "print", "filament", or "printer")

#### Project Tools

- **load_file(path)**: Load a 3D model file
- **slice()**: Start slicing the current model
- **export_gcode(path)**: Export G-code to a file
- **get_status()**: Get SuperSlicer status

### Example MCP Session

```python
# Connect to SuperSlicer
status = await get_status()
# Returns: "SuperSlicer Status: Version: 2.5.59, Model loaded: false, Object count: 0"

# Load a model
await load_file("/path/to/model.stl")

# Configure print settings
await batch_config('{
    "layer_height": "0.2",
    "infill_density": "20",
    "print_speed": "60"
}')

# Slice the model
await slice()

# Export G-code
await export_gcode("/path/to/output.gcode")
```

## Configuration Keys Reference

### Common Print Settings
- `layer_height`: Layer height in mm (0.05-0.35)
- `first_layer_height`: First layer height (mm or %)
- `perimeters`: Number of perimeters (1-10)
- `fill_density`: Infill density (0-100%)
- `fill_pattern`: Infill pattern (rectilinear, grid, triangles, etc.)
- `print_speed`: Default print speed (mm/s)

### Filament Settings
- `filament_diameter`: Filament diameter in mm
- `temperature`: Extruder temperature (°C)
- `bed_temperature`: Bed temperature (°C)
- `extrusion_multiplier`: Flow multiplier (0.9-1.1)

### Printer Settings
- `nozzle_diameter`: Nozzle diameter in mm
- `retract_length`: Retraction length (mm)
- `retract_speed`: Retraction speed (mm/s)

## Security Considerations

1. **Local-only by default**: ConfigServer binds to localhost only
2. **Authentication**: Consider adding token-based authentication for production use
3. **Input validation**: All configuration values are validated before applying
4. **Rate limiting**: Consider implementing rate limiting for API calls

## Troubleshooting

### ConfigServer not starting
- Check that port 21987 is not already in use
- Verify Boost.Asio is properly linked
- Check SuperSlicer logs for error messages

### MCP Server connection issues
- Ensure SuperSlicer is running with ConfigServer enabled
- Verify firewall settings allow localhost connections
- Check that the port numbers match

### Configuration changes not applying
- Some settings require re-slicing to take effect
- Certain printer settings may be locked during printing
- Check SuperSlicer logs for validation errors

## Future Enhancements

- WebSocket support for real-time updates
- Authentication and authorization
- Multi-instance support
- Configuration profiles and templates
- Scripting interface for complex workflows
- Integration with CI/CD pipelines

## Contributing

Contributions are welcome! Please submit pull requests with:
- Clear description of changes
- Test coverage for new features
- Documentation updates
- Example usage

## License

This MCP integration follows SuperSlicer's AGPLv3 license.