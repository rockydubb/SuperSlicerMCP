#!/usr/bin/env python3
"""
SuperSlicer MCP Server

This MCP (Model Context Protocol) server provides an interface to control
SuperSlicer instances in real-time by communicating with the ConfigServer
running inside SuperSlicer.

The server exposes tools for:
- Reading and modifying configuration values
- Managing presets
- Controlling slicing and export operations
- Loading files
- Monitoring status

Usage:
    python mcp_server.py [--port PORT] [--superslicer-port SLICER_PORT]
"""

import asyncio
import json
import socket
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

# MCP SDK imports
try:
    from mcp import Server, Tool
    from mcp.types import TextContent, ImageContent, EmbeddedResource
    from mcp.server.stdio import stdio_server
except ImportError:
    print("MCP SDK not found. Please install it with: pip install mcp")
    exit(1)

logger = logging.getLogger(__name__)

class ConfigType(Enum):
    """Configuration parameter types in SuperSlicer"""
    PRINT = "print"
    FILAMENT = "filament"
    PRINTER = "printer"

@dataclass
class SuperSlicerConnection:
    """Represents a connection to a SuperSlicer instance"""
    host: str = "localhost"
    port: int = 21987
    timeout: float = 5.0
    
    def send_command(self, command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a command to SuperSlicer and return the response"""
        request = {
            "command": command,
            "params": params or {}
        }
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect((self.host, self.port))
                
                # Send request as JSON with newline terminator
                request_str = json.dumps(request) + "\n"
                sock.sendall(request_str.encode('utf-8'))
                
                # Receive response (read until newline)
                response_data = b""
                while True:
                    chunk = sock.recv(1024)
                    if not chunk:
                        break
                    response_data += chunk
                    if b"\n" in response_data:
                        break
                
                response_str = response_data.decode('utf-8').strip()
                return json.loads(response_str)
                
        except socket.timeout:
            return {"error": "Connection timeout"}
        except socket.error as e:
            return {"error": f"Connection error: {str(e)}"}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}

class SuperSlicerMCPServer:
    """MCP Server for SuperSlicer control"""
    
    def __init__(self, superslicer_port: int = 21987):
        self.server = Server("superslicer-mcp")
        self.connection = SuperSlicerConnection(port=superslicer_port)
        self._setup_tools()
        self._setup_resources()
    
    def _setup_tools(self):
        """Register all available tools"""
        
        @self.server.tool()
        async def get_config(key: str) -> str:
            """Get a configuration value from SuperSlicer
            
            Args:
                key: Configuration key (e.g., 'layer_height', 'nozzle_diameter')
            
            Returns:
                Current value of the configuration parameter
            """
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.connection.send_command, "get_config", {"key": key}
            )
            
            if "error" in result:
                return f"Error: {result['error']}"
            
            return f"Config {result.get('key', key)}: {result.get('value', 'unknown')} (type: {result.get('type', 'unknown')})"
        
        @self.server.tool()
        async def set_config(key: str, value: str) -> str:
            """Set a configuration value in SuperSlicer
            
            Args:
                key: Configuration key (e.g., 'layer_height')
                value: New value for the configuration parameter
            
            Returns:
                Confirmation of the change
            """
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.connection.send_command, "set_config", {"key": key, "value": value}
            )
            
            if "error" in result:
                return f"Error: {result['error']}"
            
            if result.get("success"):
                return f"Successfully set {key} to {value}"
            else:
                return f"Failed to set {key}"
        
        @self.server.tool()
        async def list_presets() -> str:
            """List all available presets in SuperSlicer
            
            Returns:
                List of available presets grouped by type
            """
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.connection.send_command, "list_presets", {}
            )
            
            if "error" in result:
                return f"Error: {result['error']}"
            
            presets = result.get("presets", [])
            if not presets:
                return "No presets found"
            
            # Group presets by type
            grouped = {}
            for preset in presets:
                preset_type = preset.get("type", "unknown")
                if preset_type not in grouped:
                    grouped[preset_type] = []
                grouped[preset_type].append(preset.get("name", "unnamed"))
            
            output = ["Available presets:"]
            for preset_type, names in grouped.items():
                output.append(f"\n{preset_type.capitalize()} presets:")
                for name in names:
                    output.append(f"  - {name}")
            
            return "\n".join(output)
        
        @self.server.tool()
        async def get_preset(preset_type: str = "print") -> str:
            """Get information about the current preset
            
            Args:
                preset_type: Type of preset ('print', 'filament', or 'printer')
            
            Returns:
                Information about the current preset
            """
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.connection.send_command, "get_preset", {"type": preset_type}
            )
            
            if "error" in result:
                return f"Error: {result['error']}"
            
            return (f"Current {preset_type} preset: {result.get('name', 'unknown')}\n"
                   f"  Modified: {result.get('is_dirty', False)}\n"
                   f"  System preset: {result.get('is_system', False)}")
        
        @self.server.tool()
        async def slice() -> str:
            """Start slicing the current model
            
            Returns:
                Status message
            """
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.connection.send_command, "slice", {}
            )
            
            if "error" in result:
                return f"Error: {result['error']}"
            
            return result.get("message", "Slicing command sent")
        
        @self.server.tool()
        async def export_gcode(path: str) -> str:
            """Export G-code to a file
            
            Args:
                path: File path where to save the G-code
            
            Returns:
                Status message
            """
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.connection.send_command, "export", {"path": path}
            )
            
            if "error" in result:
                return f"Error: {result['error']}"
            
            if result.get("success"):
                return f"G-code exported to {result.get('path', path)}"
            else:
                return "Failed to export G-code"
        
        @self.server.tool()
        async def load_file(path: str) -> str:
            """Load a 3D model file into SuperSlicer
            
            Args:
                path: Path to the file to load (STL, OBJ, 3MF, etc.)
            
            Returns:
                Status message
            """
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.connection.send_command, "load_file", {"path": path}
            )
            
            if "error" in result:
                return f"Error: {result['error']}"
            
            if result.get("success"):
                return f"Successfully loaded {result.get('path', path)}"
            else:
                return "Failed to load file"
        
        @self.server.tool()
        async def get_status() -> str:
            """Get the current status of SuperSlicer
            
            Returns:
                Status information including version and loaded models
            """
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.connection.send_command, "get_status", {}
            )
            
            if "error" in result:
                return f"Error: {result['error']}"
            
            return (f"SuperSlicer Status:\n"
                   f"  Version: {result.get('app_version', 'unknown')}\n"
                   f"  Model loaded: {result.get('has_model', False)}\n"
                   f"  Object count: {result.get('object_count', 0)}")
        
        @self.server.tool()
        async def batch_config(configs: str) -> str:
            """Set multiple configuration values at once
            
            Args:
                configs: JSON string with key-value pairs (e.g., '{"layer_height": "0.2", "infill_density": "20"}')
            
            Returns:
                Status of each configuration change
            """
            try:
                config_dict = json.loads(configs)
            except json.JSONDecodeError:
                return "Error: Invalid JSON format for configs"
            
            results = []
            for key, value in config_dict.items():
                result = await asyncio.get_event_loop().run_in_executor(
                    None, self.connection.send_command, "set_config", {"key": key, "value": str(value)}
                )
                
                if "error" in result:
                    results.append(f"  {key}: Error - {result['error']}")
                elif result.get("success"):
                    results.append(f"  {key}: Set to {value}")
                else:
                    results.append(f"  {key}: Failed")
            
            return "Batch configuration results:\n" + "\n".join(results)
    
    def _setup_resources(self):
        """Register available resources"""
        
        @self.server.resource("config_keys")
        async def get_config_keys() -> str:
            """Common SuperSlicer configuration keys reference"""
            return """
Common SuperSlicer Configuration Keys:

Print Settings:
- layer_height: Layer height in mm (0.05-0.35)
- first_layer_height: First layer height (mm or %)
- perimeters: Number of perimeters (1-10)
- top_solid_layers: Number of solid top layers
- bottom_solid_layers: Number of solid bottom layers
- fill_density: Infill density (0-100%)
- fill_pattern: Infill pattern (rectilinear, grid, triangles, etc.)
- print_speed: Default print speed (mm/s)
- travel_speed: Travel speed (mm/s)
- first_layer_speed: First layer speed (mm/s or %)

Filament Settings:
- filament_diameter: Filament diameter in mm
- extrusion_multiplier: Flow multiplier (0.9-1.1)
- temperature: Extruder temperature (°C)
- first_layer_temperature: First layer temperature (°C)
- bed_temperature: Bed temperature (°C)
- first_layer_bed_temperature: First layer bed temperature (°C)

Printer Settings:
- nozzle_diameter: Nozzle diameter in mm
- z_offset: Z offset adjustment
- retract_length: Retraction length (mm)
- retract_speed: Retraction speed (mm/s)
- max_print_speed: Maximum print speed (mm/s)
- max_volumetric_speed: Maximum volumetric speed (mm³/s)

Support Settings:
- support_material: Enable supports (0/1)
- support_material_pattern: Support pattern
- support_material_spacing: Support spacing (mm)
- support_material_contact_distance: Contact Z distance (mm)
"""
        
        @self.server.resource("mcp_usage")
        async def get_usage_guide() -> str:
            """How to use the SuperSlicer MCP server"""
            return """
SuperSlicer MCP Server Usage Guide:

1. Start SuperSlicer with ConfigServer enabled (port 21987 by default)
2. Start this MCP server
3. Connect your MCP client

Available Tools:
- get_config(key): Get a configuration value
- set_config(key, value): Set a configuration value
- list_presets(): List all available presets
- get_preset(type): Get current preset info
- slice(): Start slicing
- export_gcode(path): Export G-code
- load_file(path): Load a 3D model
- get_status(): Get SuperSlicer status
- batch_config(configs): Set multiple configs at once

Example Commands:
- Get layer height: get_config("layer_height")
- Set layer height: set_config("layer_height", "0.2")
- Batch config: batch_config('{"layer_height": "0.2", "infill_density": "20"}')
- Load model: load_file("/path/to/model.stl")
- Start slicing: slice()
- Export: export_gcode("/path/to/output.gcode")
"""
    
    async def run(self):
        """Run the MCP server"""
        # Use stdio transport for MCP
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream)

async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="SuperSlicer MCP Server")
    parser.add_argument("--superslicer-port", type=int, default=21987,
                       help="Port where SuperSlicer ConfigServer is listening")
    parser.add_argument("--debug", action="store_true",
                       help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Create and run server
    server = SuperSlicerMCPServer(superslicer_port=args.superslicer_port)
    
    logger.info(f"Starting SuperSlicer MCP Server (connecting to SuperSlicer on port {args.superslicer_port})")
    
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())