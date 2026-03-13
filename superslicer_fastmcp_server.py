#!/usr/bin/env python3
"""
SuperSlicer FastMCP Server

A high-performance MCP (Model Context Protocol) server built with FastMCP 
that provides real-time control over SuperSlicer instances through the 
embedded ConfigServer.

This server communicates with the ConfigServer running inside SuperSlicer
to enable live configuration changes, slicing control, and project management.

Features:
- Live configuration reading and modification
- Preset management (print, filament, printer)
- 3D model loading and manipulation
- Slicing and G-code export control
- Real-time status monitoring
- Batch configuration updates

Requirements:
- fastmcp (pip install fastmcp)
- Python 3.8+
- SuperSlicer running with ConfigServer enabled

Usage:
    uvicorn superslicer_fastmcp_server:app --host 0.0.0.0 --port 3000
    
Or with custom SuperSlicer port:
    CONFIG_SERVER_PORT=21987 uvicorn superslicer_fastmcp_server:app
"""

import asyncio
import json
import socket
import logging
import os
import httpx
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from pathlib import Path
from enum import Enum

from fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
SUPERSLICER_HOST = os.getenv("CONFIG_SERVER_HOST", "localhost")
SUPERSLICER_PORT = int(os.getenv("CONFIG_SERVER_PORT", "21987"))
CONNECTION_TIMEOUT = float(os.getenv("CONNECTION_TIMEOUT", "5.0"))

# Initialize FastMCP
mcp = FastMCP(
    "SuperSlicer Live Control",
    dependencies=["fastmcp>=0.1.0"]
)

class ConfigType(Enum):
    """Configuration types in SuperSlicer"""
    PRINT = "print"
    FILAMENT = "filament"
    PRINTER = "printer"
    GLOBAL = "global"

class SuperSlicerClient:
    """Client for communicating with SuperSlicer's ConfigServer"""
    
    def __init__(self, host: str = SUPERSLICER_HOST, port: int = SUPERSLICER_PORT, timeout: float = CONNECTION_TIMEOUT):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._last_error = None
    
    async def send_command(self, command: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a command to SuperSlicer ConfigServer asynchronously"""
        request = {
            "command": command,
            "params": params or {}
        }
        
        try:
            # Run socket communication in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._send_command_sync, request)
            return result
        except Exception as e:
            logger.error(f"Command failed: {e}")
            self._last_error = str(e)
            return {"error": str(e), "success": False}
    
    def _send_command_sync(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous socket communication with SuperSlicer"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect((self.host, self.port))
                
                # Send JSON request with newline terminator
                request_str = json.dumps(request) + "\n"
                sock.sendall(request_str.encode('utf-8'))
                
                # Receive response (read until newline or max buffer)
                response_data = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                    if b"\n" in response_data:
                        break
                
                response_str = response_data.decode('utf-8').strip()
                if not response_str:
                    return {"error": "Empty response from server"}
                
                return json.loads(response_str)
                
        except socket.timeout:
            return {"error": "Connection timeout - is SuperSlicer running with ConfigServer enabled?"}
        except socket.error as e:
            return {"error": f"Connection error: {str(e)}. Make sure SuperSlicer is running with --enable-config-server"}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response: {str(e)}"}
    
    async def is_connected(self) -> bool:
        """Check if SuperSlicer is accessible"""
        result = await self.send_command("ping")
        return result.get("success", False) or result.get("pong", False)

# Global client instance
client = SuperSlicerClient()

# Track discovered instances
_discovered_instances = []
_selected_instance_port = SUPERSLICER_PORT

# ===== Instance Discovery and Management =====

@mcp.tool()
async def discover_instances(default_port: int = 21987) -> Dict[str, Any]:
    """Discover all running SuperSlicer instances
    
    Queries the instance registry to find all active SuperSlicer instances.
    Each instance registers itself when starting with ConfigServer enabled.
    
    Args:
        default_port: Port to query for instance list (default: 21987)
    
    Returns:
        List of discovered instances with their details
    """
    global _discovered_instances
    
    try:
        async with httpx.AsyncClient(timeout=CONNECTION_TIMEOUT) as http_client:
            response = await http_client.get(f"http://{SUPERSLICER_HOST}:{default_port}/api/list_instances")
            response.raise_for_status()
            data = response.json()
            
            instances = data.get("instances", [])
            _discovered_instances = instances
            
            return {
                "success": True,
                "count": len(instances),
                "instances": instances,
                "message": f"Found {len(instances)} active SuperSlicer instance(s)"
            }
    except httpx.HTTPError as e:
        return {
            "success": False,
            "count": 0,
            "instances": [],
            "error": f"Failed to discover instances: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "count": 0,
            "instances": [],
            "error": f"Unexpected error: {str(e)}"
        }

@mcp.tool()
async def list_instances() -> Dict[str, Any]:
    """List all discovered SuperSlicer instances
    
    Returns the cached list of instances from the last discovery.
    Call discover_instances() first to refresh the list.
    
    Returns:
        List of previously discovered instances
    """
    global _discovered_instances
    
    if not _discovered_instances:
        # Try to discover if we haven't yet
        discovery = await discover_instances()
        if not discovery.get("success"):
            return {
                "success": False,
                "instances": [],
                "message": "No instances cached. Call discover_instances() first or check if SuperSlicer is running."
            }
    
    return {
        "success": True,
        "count": len(_discovered_instances),
        "instances": _discovered_instances,
        "selected_port": _selected_instance_port
    }

@mcp.tool()
async def select_instance(instance_id: Optional[str] = None, port: Optional[int] = None) -> Dict[str, Any]:
    """Select a specific SuperSlicer instance to control
    
    After selection, all subsequent commands will be sent to this instance.
    You can select by instance_id or port number.
    
    Args:
        instance_id: Instance ID (e.g., "12345_21987")
        port: Port number of the instance
    
    Returns:
        Confirmation of instance selection
    """
    global _selected_instance_port, client, _discovered_instances
    
    if not instance_id and not port:
        return {"error": "Must specify either instance_id or port"}
    
    # Ensure we have discovered instances
    if not _discovered_instances:
        await discover_instances()
    
    # Find the instance
    target_instance = None
    if instance_id:
        target_instance = next((inst for inst in _discovered_instances if inst.get("instance_id") == instance_id), None)
    elif port:
        target_instance = next((inst for inst in _discovered_instances if inst.get("port") == port), None)
    
    if not target_instance:
        return {
            "success": False,
            "error": f"Instance not found. Available instances: {[inst.get('instance_id') for inst in _discovered_instances]}"
        }
    
    # Update the selected port and recreate client
    _selected_instance_port = target_instance["port"]
    client = SuperSlicerClient(host=SUPERSLICER_HOST, port=_selected_instance_port, timeout=CONNECTION_TIMEOUT)
    
    # Verify connection
    is_connected = await client.is_connected()
    
    return {
        "success": is_connected,
        "selected_instance": target_instance,
        "instance_id": target_instance["instance_id"],
        "port": target_instance["port"],
        "process_id": target_instance.get("process_id"),
        "project_name": target_instance.get("project_name", "No project loaded"),
        "message": f"Selected instance {target_instance['instance_id']}" if is_connected else "Failed to connect to selected instance"
    }

@mcp.tool()
async def get_current_instance() -> Dict[str, Any]:
    """Get information about the currently selected instance
    
    Returns:
        Details of the active instance
    """
    global _selected_instance_port, _discovered_instances
    
    current = next(
        (inst for inst in _discovered_instances if inst.get("port") == _selected_instance_port),
        None
    )
    
    if current:
        return {
            "success": True,
            "instance": current,
            "connected": await client.is_connected()
        }
    
    return {
        "success": False,
        "port": _selected_instance_port,
        "message": "No instance currently selected or instance info unavailable. Call discover_instances() and select_instance()."
    }

# ===== Connection Management =====

@mcp.tool()
async def check_connection() -> Dict[str, Any]:
    """Check if SuperSlicer is running and accessible
    
    Verifies that the ConfigServer is running and responding to commands.
    """
    is_connected = await client.is_connected()
    if is_connected:
        status = await client.send_command("get_status")
        return {
            "connected": True,
            "host": client.host,
            "port": client.port,
            "version": status.get("version", "unknown"),
            "status": status
        }
    return {
        "connected": False,
        "host": client.host,
        "port": client.port,
        "error": "Cannot connect to SuperSlicer. Ensure it's running with --enable-config-server"
    }

# ===== Configuration Management =====

@mcp.tool()
async def get_config(key: str, config_type: str = "print") -> Dict[str, Any]:
    """Get a configuration value from SuperSlicer
    
    Args:
        key: Configuration key (e.g., 'layer_height', 'nozzle_diameter')
        config_type: Type of config ('print', 'filament', 'printer', 'global')
    
    Returns:
        Dictionary with the configuration value and metadata
    """
    result = await client.send_command("get_config", {
        "key": key,
        "type": config_type
    })
    
    if result.get("success"):
        return {
            "key": key,
            "value": result.get("value"),
            "type": result.get("type", "unknown"),
            "config_type": config_type,
            "label": result.get("label", key),
            "tooltip": result.get("tooltip", ""),
            "min": result.get("min"),
            "max": result.get("max"),
            "default": result.get("default")
        }
    return {"error": result.get("error", "Failed to get configuration")}

@mcp.tool()
async def set_config(key: str, value: Union[str, int, float, bool], config_type: str = "print") -> Dict[str, Any]:
    """Set a configuration value in SuperSlicer
    
    Args:
        key: Configuration key (e.g., 'layer_height')
        value: New value for the configuration
        config_type: Type of config ('print', 'filament', 'printer', 'global')
    
    Returns:
        Confirmation of the configuration change
    """
    # Convert value to string for transmission
    value_str = str(value).lower() if isinstance(value, bool) else str(value)
    
    result = await client.send_command("set_config", {
        "key": key,
        "value": value_str,
        "type": config_type
    })
    
    if result.get("success"):
        return {
            "success": True,
            "key": key,
            "new_value": value_str,
            "config_type": config_type,
            "message": f"Successfully set {key} to {value_str}"
        }
    return {
        "success": False,
        "error": result.get("error", "Failed to set configuration"),
        "key": key
    }

@mcp.tool()
async def batch_config(settings: Dict[str, Union[str, int, float, bool]], config_type: str = "print") -> Dict[str, Any]:
    """Set multiple configuration values at once
    
    Args:
        settings: Dictionary of key-value pairs to set
        config_type: Type of config ('print', 'filament', 'printer', 'global')
    
    Returns:
        Summary of changes made
    """
    # Convert all values to strings
    string_settings = {k: str(v).lower() if isinstance(v, bool) else str(v) 
                      for k, v in settings.items()}
    
    result = await client.send_command("batch_config", {
        "settings": string_settings,
        "type": config_type
    })
    
    if result.get("success"):
        return {
            "success": True,
            "updated": result.get("updated", []),
            "failed": result.get("failed", []),
            "count": len(result.get("updated", [])),
            "config_type": config_type,
            "message": f"Updated {len(result.get('updated', []))} settings"
        }
    return {
        "success": False,
        "error": result.get("error", "Batch update failed")
    }

@mcp.tool()
async def search_config(search_term: str, config_type: Optional[str] = None) -> Dict[str, Any]:
    """Search for configuration keys matching a term
    
    Args:
        search_term: Term to search for in configuration keys
        config_type: Optional config type to limit search ('print', 'filament', 'printer')
    
    Returns:
        List of matching configuration keys with their current values
    """
    params = {"search": search_term}
    if config_type:
        params["type"] = config_type
    
    result = await client.send_command("search_config", params)
    
    if result.get("success"):
        return {
            "search_term": search_term,
            "matches": result.get("matches", []),
            "count": len(result.get("matches", [])),
            "config_type": config_type or "all"
        }
    return {"error": result.get("error", "Search failed")}

# ===== Preset Management =====

@mcp.tool()
async def list_presets(preset_type: Optional[str] = None) -> Dict[str, Any]:
    """List all available presets
    
    Args:
        preset_type: Optional filter by type ('print', 'filament', 'printer')
    
    Returns:
        Dictionary of available presets grouped by type
    """
    params = {}
    if preset_type:
        params["type"] = preset_type
    
    result = await client.send_command("list_presets", params)
    
    if result.get("success"):
        presets = result.get("presets", {})
        return {
            "presets": presets,
            "total_count": sum(len(p) for p in presets.values()),
            "types": list(presets.keys())
        }
    return {"error": result.get("error", "Failed to list presets")}

@mcp.tool()
async def get_preset(preset_type: str = "print") -> Dict[str, Any]:
    """Get information about the current active preset
    
    Args:
        preset_type: Type of preset ('print', 'filament', or 'printer')
    
    Returns:
        Information about the current preset
    """
    result = await client.send_command("get_preset", {"type": preset_type})
    
    if result.get("success"):
        return {
            "type": preset_type,
            "name": result.get("name", "unknown"),
            "is_dirty": result.get("is_dirty", False),
            "is_system": result.get("is_system", False),
            "is_compatible": result.get("is_compatible", True),
            "vendor": result.get("vendor"),
            "inherits": result.get("inherits"),
            "file_path": result.get("file_path")
        }
    return {"error": result.get("error", "Failed to get preset info")}

@mcp.tool()
async def select_preset(preset_name: str, preset_type: str = "print") -> Dict[str, Any]:
    """Select and activate a preset
    
    Args:
        preset_name: Name of the preset to activate
        preset_type: Type of preset ('print', 'filament', or 'printer')
    
    Returns:
        Confirmation of preset activation
    """
    result = await client.send_command("select_preset", {
        "name": preset_name,
        "type": preset_type
    })
    
    if result.get("success"):
        return {
            "success": True,
            "preset_name": preset_name,
            "preset_type": preset_type,
            "message": f"Successfully activated {preset_type} preset: {preset_name}"
        }
    return {
        "success": False,
        "error": result.get("error", "Failed to select preset")
    }

@mcp.tool()
async def save_preset(preset_name: str, preset_type: str = "print", overwrite: bool = False) -> Dict[str, Any]:
    """Save current configuration as a new preset
    
    Args:
        preset_name: Name for the new preset
        preset_type: Type of preset ('print', 'filament', or 'printer')
        overwrite: Whether to overwrite if preset exists
    
    Returns:
        Confirmation of preset creation
    """
    result = await client.send_command("save_preset", {
        "name": preset_name,
        "type": preset_type,
        "overwrite": overwrite
    })
    
    if result.get("success"):
        return {
            "success": True,
            "preset_name": preset_name,
            "preset_type": preset_type,
            "message": f"Successfully saved {preset_type} preset: {preset_name}"
        }
    return {
        "success": False,
        "error": result.get("error", "Failed to save preset")
    }

# ===== Project and Model Management =====

@mcp.tool()
async def load_file(file_path: str, center: bool = True, auto_arrange: bool = True) -> Dict[str, Any]:
    """Load a 3D model file into SuperSlicer
    
    Args:
        file_path: Path to the 3D file (STL, OBJ, 3MF, etc.)
        center: Whether to center the model on the build plate
        auto_arrange: Whether to auto-arrange if multiple objects
    
    Returns:
        Information about the loaded model
    """
    # Validate file exists
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    
    result = await client.send_command("load_file", {
        "path": str(path.absolute()),
        "center": center,
        "auto_arrange": auto_arrange
    })
    
    if result.get("success"):
        return {
            "success": True,
            "file_path": file_path,
            "object_count": result.get("object_count", 0),
            "volume_count": result.get("volume_count", 0),
            "bounding_box": result.get("bounding_box"),
            "message": f"Successfully loaded {path.name}"
        }
    return {
        "success": False,
        "error": result.get("error", "Failed to load file")
    }

@mcp.tool()
async def clear_plate() -> Dict[str, Any]:
    """Clear all objects from the build plate
    
    Returns:
        Confirmation of plate clearing
    """
    result = await client.send_command("clear_plate")
    
    if result.get("success"):
        return {
            "success": True,
            "message": "Build plate cleared"
        }
    return {
        "success": False,
        "error": result.get("error", "Failed to clear plate")
    }

@mcp.tool()
async def arrange_objects(spacing: float = 5.0) -> Dict[str, Any]:
    """Auto-arrange objects on the build plate
    
    Args:
        spacing: Spacing between objects in mm
    
    Returns:
        Information about the arrangement
    """
    result = await client.send_command("arrange", {"spacing": spacing})
    
    if result.get("success"):
        return {
            "success": True,
            "object_count": result.get("object_count", 0),
            "spacing": spacing,
            "message": "Objects arranged successfully"
        }
    return {
        "success": False,
        "error": result.get("error", "Failed to arrange objects")
    }

# ===== Slicing and Export =====

@mcp.tool()
async def slice(sequential: bool = False) -> Dict[str, Any]:
    """Start slicing the current model(s)
    
    Args:
        sequential: Whether to slice objects sequentially
    
    Returns:
        Slicing status and statistics
    """
    result = await client.send_command("slice", {"sequential": sequential})
    
    if result.get("success"):
        return {
            "success": True,
            "slicing_time": result.get("slicing_time"),
            "layer_count": result.get("layer_count"),
            "estimated_print_time": result.get("estimated_print_time"),
            "filament_used": result.get("filament_used"),
            "filament_cost": result.get("filament_cost"),
            "message": "Slicing completed successfully"
        }
    return {
        "success": False,
        "error": result.get("error", "Slicing failed")
    }

@mcp.tool()
async def export_gcode(output_path: str, include_thumbnails: bool = True) -> Dict[str, Any]:
    """Export sliced model as G-code
    
    Args:
        output_path: Path where to save the G-code file
        include_thumbnails: Whether to include preview thumbnails
    
    Returns:
        Export confirmation and file information
    """
    result = await client.send_command("export_gcode", {
        "path": output_path,
        "include_thumbnails": include_thumbnails
    })
    
    if result.get("success"):
        file_size = result.get("file_size", 0)
        return {
            "success": True,
            "output_path": output_path,
            "file_size": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2) if file_size else 0,
            "line_count": result.get("line_count"),
            "message": f"G-code exported to {output_path}"
        }
    return {
        "success": False,
        "error": result.get("error", "Export failed")
    }

@mcp.tool()
async def export_3mf(output_path: str, include_config: bool = True) -> Dict[str, Any]:
    """Export project as 3MF file
    
    Args:
        output_path: Path where to save the 3MF file
        include_config: Whether to include configuration in the file
    
    Returns:
        Export confirmation
    """
    result = await client.send_command("export_3mf", {
        "path": output_path,
        "include_config": include_config
    })
    
    if result.get("success"):
        return {
            "success": True,
            "output_path": output_path,
            "file_size": result.get("file_size"),
            "message": f"Project exported to {output_path}"
        }
    return {
        "success": False,
        "error": result.get("error", "Export failed")
    }

# ===== Status and Information =====

@mcp.tool()
async def get_status() -> Dict[str, Any]:
    """Get comprehensive SuperSlicer status
    
    Returns:
        Detailed status including version, loaded models, and current state
    """
    result = await client.send_command("get_status")
    
    if result.get("success") or "version" in result:
        return {
            "version": result.get("version", "unknown"),
            "model_loaded": result.get("model_loaded", False),
            "object_count": result.get("object_count", 0),
            "is_sliced": result.get("is_sliced", False),
            "current_preset": {
                "print": result.get("current_print_preset"),
                "filament": result.get("current_filament_preset"),
                "printer": result.get("current_printer_preset")
            },
            "plate_dimensions": result.get("plate_dimensions"),
            "memory_usage": result.get("memory_usage"),
            "uptime": result.get("uptime")
        }
    return {"error": result.get("error", "Failed to get status")}

@mcp.tool()
async def get_object_info(object_index: int = 0) -> Dict[str, Any]:
    """Get information about a specific object on the plate
    
    Args:
        object_index: Index of the object (0-based)
    
    Returns:
        Detailed object information
    """
    result = await client.send_command("get_object_info", {"index": object_index})
    
    if result.get("success"):
        return {
            "index": object_index,
            "name": result.get("name"),
            "volume_count": result.get("volume_count"),
            "instance_count": result.get("instance_count"),
            "bounding_box": result.get("bounding_box"),
            "position": result.get("position"),
            "rotation": result.get("rotation"),
            "scale": result.get("scale"),
            "volume": result.get("volume"),
            "is_printable": result.get("is_printable", True)
        }
    return {"error": result.get("error", "Failed to get object info")}

@mcp.tool()
async def get_print_statistics() -> Dict[str, Any]:
    """Get detailed print statistics for the current sliced model
    
    Returns:
        Comprehensive print statistics
    """
    result = await client.send_command("get_print_stats")
    
    if result.get("success"):
        return {
            "estimated_time": result.get("estimated_time"),
            "estimated_time_formatted": result.get("estimated_time_formatted"),
            "filament_used": result.get("filament_used"),
            "filament_cost": result.get("filament_cost"),
            "layer_count": result.get("layer_count"),
            "layer_height": result.get("layer_height"),
            "first_layer_height": result.get("first_layer_height"),
            "object_height": result.get("object_height"),
            "support_material": result.get("support_material"),
            "brim": result.get("brim"),
            "raft": result.get("raft")
        }
    return {"error": result.get("error", "Model not sliced or statistics unavailable")}

# ===== Advanced Operations =====

@mcp.tool()
async def validate_config(config_type: str = "print") -> Dict[str, Any]:
    """Validate current configuration for conflicts or issues
    
    Args:
        config_type: Type of config to validate ('print', 'filament', 'printer')
    
    Returns:
        Validation results with any warnings or errors
    """
    result = await client.send_command("validate_config", {"type": config_type})
    
    if result.get("success"):
        return {
            "valid": result.get("valid", True),
            "warnings": result.get("warnings", []),
            "errors": result.get("errors", []),
            "suggestions": result.get("suggestions", []),
            "config_type": config_type
        }
    return {"error": result.get("error", "Validation failed")}

@mcp.tool()
async def reset_to_defaults(config_type: str = "print", confirm: bool = False) -> Dict[str, Any]:
    """Reset configuration to default values
    
    Args:
        config_type: Type of config to reset ('print', 'filament', 'printer')
        confirm: Must be True to actually perform the reset
    
    Returns:
        Confirmation of reset operation
    """
    if not confirm:
        return {
            "success": False,
            "error": "Set confirm=True to actually reset to defaults"
        }
    
    result = await client.send_command("reset_defaults", {"type": config_type})
    
    if result.get("success"):
        return {
            "success": True,
            "config_type": config_type,
            "message": f"Configuration reset to defaults for {config_type}"
        }
    return {
        "success": False,
        "error": result.get("error", "Reset failed")
    }

@mcp.tool()
async def execute_gcode_macro(macro_name: str) -> Dict[str, Any]:
    """Execute a G-code macro or custom G-code
    
    Args:
        macro_name: Name of the macro to execute
    
    Returns:
        Execution result
    """
    result = await client.send_command("execute_macro", {"name": macro_name})
    
    if result.get("success"):
        return {
            "success": True,
            "macro_name": macro_name,
            "output": result.get("output"),
            "message": f"Macro {macro_name} executed successfully"
        }
    return {
        "success": False,
        "error": result.get("error", "Macro execution failed")
    }

# ===== Resources (for MCP resource exposure) =====

@mcp.resource("superslicer://config/print")
async def get_print_config_resource() -> str:
    """Get all print configuration as a resource"""
    result = await client.send_command("get_all_config", {"type": "print"})
    return json.dumps(result.get("config", {}), indent=2)

@mcp.resource("superslicer://config/filament")
async def get_filament_config_resource() -> str:
    """Get all filament configuration as a resource"""
    result = await client.send_command("get_all_config", {"type": "filament"})
    return json.dumps(result.get("config", {}), indent=2)

@mcp.resource("superslicer://config/printer")  
async def get_printer_config_resource() -> str:
    """Get all printer configuration as a resource"""
    result = await client.send_command("get_all_config", {"type": "printer"})
    return json.dumps(result.get("config", {}), indent=2)

@mcp.resource("superslicer://status")
async def get_status_resource() -> str:
    """Get current SuperSlicer status as a resource"""
    status = await get_status()
    return json.dumps(status, indent=2)

# ===== Server lifecycle =====

@mcp.server.start()
async def on_start():
    """Initialize the MCP server"""
    logger.info(f"SuperSlicer FastMCP Server starting...")
    logger.info(f"Connecting to ConfigServer at {SUPERSLICER_HOST}:{SUPERSLICER_PORT}")
    
    # Test connection
    if await client.is_connected():
        logger.info("✓ Successfully connected to SuperSlicer ConfigServer")
    else:
        logger.warning("✗ Cannot connect to SuperSlicer - ensure it's running with --enable-config-server")

@mcp.server.stop()
async def on_stop():
    """Cleanup on server shutdown"""
    logger.info("SuperSlicer FastMCP Server stopping...")

# Export the FastMCP app
app = mcp.app

if __name__ == "__main__":
    import uvicorn
    # Run with uvicorn for development
    uvicorn.run(app, host="0.0.0.0", port=3000)