#!/usr/bin/env python3
"""
SuperSlicer MCP Server
Provides tools to read and edit SuperSlicer configuration files.
"""

import json
from pathlib import Path
from typing import Dict, List, Any
from fastmcp import FastMCP

# SuperSlicer config directory
CONFIG_DIR = Path.home() / ".config" / "SuperSlicer"

# Initialize FastMCP server
mcp = FastMCP("SuperSlicer Config")


def get_config_categories() -> List[str]:
    """Get list of configuration categories (subdirectories)."""
    categories = []
    if CONFIG_DIR.exists():
        for item in CONFIG_DIR.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                categories.append(item.name)
    return sorted(categories)


def list_presets(category: str) -> List[Dict[str, Any]]:
    """List all presets in a category."""
    category_dir = CONFIG_DIR / category
    if not category_dir.exists():
        return []
    
    presets = []
    for ini_file in category_dir.glob("*.ini"):
        presets.append({
            "name": ini_file.stem,
            "path": str(ini_file),
            "size": ini_file.stat().st_size,
            "modified": ini_file.stat().st_mtime
        })
    return presets


def read_preset_config(category: str, preset_name: str) -> Dict[str, Any]:
    """Read configuration from a preset file."""
    preset_path = CONFIG_DIR / category / f"{preset_name}.ini"
    
    if not preset_path.exists():
        raise FileNotFoundError(f"Preset not found: {category}/{preset_name}")
    
    config = configparser.ConfigParser()
    config.read(preset_path)
    
    # Convert to dict
    result = {}
    for section in config.sections():
        result[section] = dict(config[section])
    
    # Also read the DEFAULT section (no section header)
    if config.defaults():
        result['_default'] = dict(config.defaults())
    
    # For SuperSlicer configs, most settings are in DEFAULT section
    # Read them directly
    with open(preset_path, 'r') as f:
        lines = f.readlines()
    
    settings = {}
    for line in lines:
        line = line.strip()
        if line.startswith('#') or not line or '=' not in line:
            continue
        if line.startswith('['):  # Section header
            continue
        key, value = line.split('=', 1)
        settings[key.strip()] = value.strip()
    
    return settings


def write_preset_config(category: str, preset_name: str, settings: Dict[str, str]) -> None:
    """Write configuration to a preset file."""
    preset_path = CONFIG_DIR / category / f"{preset_name}.ini"
    
    # Read existing file to preserve comments and order
    existing_lines = []
    if preset_path.exists():
        with open(preset_path, 'r') as f:
            existing_lines = f.readlines()
    
    # Build new content
    new_lines = []
    updated_keys = set()
    
    for line in existing_lines:
        stripped = line.strip()
        if stripped.startswith('#') or not stripped or '=' not in stripped:
            new_lines.append(line)
            continue
        
        if stripped.startswith('['):  # Section header
            new_lines.append(line)
            continue
        
        key, old_value = stripped.split('=', 1)
        key = key.strip()
        
        if key in settings:
            new_lines.append(f"{key} = {settings[key]}\n")
            updated_keys.add(key)
        else:
            new_lines.append(line)
    
    # Add new keys that weren't in the original file
    for key, value in settings.items():
        if key not in updated_keys:
            new_lines.append(f"{key} = {value}\n")
    
    # Write back
    with open(preset_path, 'w') as f:
        f.writelines(new_lines)


def search_settings(category: str, preset_name: str, search_term: str) -> Dict[str, str]:
    """Search for settings matching a term."""
    settings = read_preset_config(category, preset_name)
    return {k: v for k, v in settings.items() if search_term.lower() in k.lower()}


@mcp.tool()
def list_config_categories() -> Dict[str, List[str]]:
    """List all configuration categories (print, filament, printer, etc.)"""
    categories = get_config_categories()
    return {"categories": categories}


@mcp.tool()
def list_presets_tool(category: str) -> Dict[str, Any]:
    """List all presets in a category
    
    Args:
        category: Category name (e.g., print, filament, printer)
    """
    presets = list_presets(category)
    return {"presets": presets}


@mcp.tool()
def read_preset_tool(category: str, preset_name: str) -> Dict[str, Any]:
    """Read all settings from a preset
    
    Args:
        category: Category name (e.g., print, filament, printer)
        preset_name: Preset name (without .ini extension)
    """
    settings = read_preset_config(category, preset_name)
    return {"settings": settings}


@mcp.tool()
def update_preset_tool(category: str, preset_name: str, settings: Dict[str, str]) -> Dict[str, Any]:
    """Update one or more settings in a preset
    
    Args:
        category: Category name (e.g., print, filament, printer)
        preset_name: Preset name (without .ini extension)
        settings: Dictionary of setting_name: value pairs to update
    """
    write_preset_config(category, preset_name, settings)
    return {
        "status": "success",
        "message": f"Updated {len(settings)} setting(s) in {category}/{preset_name}",
        "updated": list(settings.keys())
    }


@mcp.tool()
def search_settings_tool(category: str, preset_name: str, search_term: str) -> Dict[str, Any]:
    """Search for settings by name in a preset
    
    Args:
        category: Category name (e.g., print, filament, printer)
        preset_name: Preset name (without .ini extension)
        search_term: Term to search for in setting names
    """
    results = search_settings(category, preset_name, search_term)
    return {
        "search_term": search_term,
        "matches": results,
        "count": len(results)
    }


@mcp.tool()
def get_main_config_tool() -> Dict[str, Any]:
    """Read main SuperSlicer.ini configuration"""
    main_config_path = CONFIG_DIR / "SuperSlicer.ini"
    if main_config_path.exists():
        settings = read_preset_config("", "SuperSlicer")
        return {"settings": settings}
    else:
        return {"error": "SuperSlicer.ini not found"}


if __name__ == "__main__":
    mcp.run()
