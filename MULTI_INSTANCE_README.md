# SuperSlicer Multi-Instance Support

This document explains how to use SuperSlicer's multi-instance discovery and management features through the MCP server.

## Overview

SuperSlicer now supports running multiple instances simultaneously, each with its own ConfigServer. The MCP server can discover, differentiate, and control multiple instances without port scanning.

## How It Works

### Instance Registry

Each SuperSlicer instance registers itself when starting with ConfigServer enabled:

1. **Registry Location**: `/tmp/superslicer_instances/` (Linux/macOS) or `%TEMP%\superslicer_instances\` (Windows)
2. **Instance Files**: Each instance creates a JSON file: `{process_id}_{port}.json`
3. **Auto-Cleanup**: Stale instance files (from dead processes) are automatically removed
4. **Lock-Free**: No file locking issues - each instance manages its own file

### Instance Information

Each instance provides:
- **Instance ID**: Unique identifier combining process ID and port (e.g., `12345_21987`)
- **Port**: HTTP ConfigServer port number
- **Process ID**: Operating system process ID
- **Start Time**: Unix timestamp of when the instance started
- **Project Name**: Currently loaded project file (if any)

## Quick Start

### 1. Start Multiple SuperSlicer Instances

```bash
# Terminal 1: Start first instance (default port 21987)
superslicer --enable-config-server

# Terminal 2: Start second instance (will auto-increment to port 21988)
superslicer --enable-config-server

# Terminal 3: Start third instance (will use port 21989)
superslicer --enable-config-server
```

### 2. Test Instance Discovery

```bash
# Run the test script
cd /home/guy/tmp/SuperSlicer
python3 test_multi_instance.py
```

### 3. Use MCP Server

```bash
# Start the MCP server
uvicorn superslicer_fastmcp_server:app --host 0.0.0.0 --port 3000
```

## API Endpoints

### List All Instances

Query any running instance to get information about all instances:

```bash
curl http://localhost:21987/api/list_instances
```

**Response:**
```json
{
  "instances": [
    {
      "instance_id": "12345_21987",
      "port": 21987,
      "process_id": 12345,
      "start_time": 1673456789,
      "project_name": "my_model.3mf"
    },
    {
      "instance_id": "12346_21988",
      "port": 21988,
      "process_id": 12346,
      "start_time": 1673456790,
      "project_name": ""
    }
  ]
}
```

### Get Instance Status

Query a specific instance by port:

```bash
curl http://localhost:21987/api/status
curl http://localhost:21988/api/status
```

## MCP Tools

The MCP server provides these tools for multi-instance management:

### 1. `discover_instances()`

Discovers all running SuperSlicer instances.

```python
result = await discover_instances()
# Returns: {"success": True, "count": 2, "instances": [...]}
```

### 2. `list_instances()`

Lists cached discovered instances.

```python
result = await list_instances()
# Returns: {"success": True, "count": 2, "instances": [...], "selected_port": 21987}
```

### 3. `select_instance()`

Selects a specific instance to control.

```python
# Select by port
await select_instance(port=21988)

# Or select by instance ID
await select_instance(instance_id="12346_21988")
```

### 4. `get_current_instance()`

Gets information about the currently selected instance.

```python
result = await get_current_instance()
# Returns: {"success": True, "instance": {...}, "connected": True}
```

## Usage Examples

### Python Example

```python
import asyncio
from superslicer_fastmcp_server import discover_instances, select_instance, get_status

async def main():
    # Discover all instances
    discovery = await discover_instances()
    print(f"Found {discovery['count']} instances")
    
    # Select the second instance
    instances = discovery['instances']
    if len(instances) > 1:
        await select_instance(port=instances[1]['port'])
        
        # Now all commands go to the second instance
        status = await get_status()
        print(f"Instance 2 status: {status}")

asyncio.run(main())
```

### CLI Example

```bash
# Discover instances
curl http://localhost:21987/api/list_instances

# Get status from each instance
curl http://localhost:21987/api/status
curl http://localhost:21988/api/status
curl http://localhost:21989/api/status
```

## Common Scenarios

### Scenario 1: Multiple Projects

Work on multiple projects simultaneously:

1. Instance 1 (port 21987): Working on `project_a.3mf`
2. Instance 2 (port 21988): Working on `project_b.3mf`
3. Instance 3 (port 21989): Testing new settings

### Scenario 2: Batch Processing

Process multiple models in parallel:

```python
async def process_all_instances():
    discovery = await discover_instances()
    
    for instance in discovery['instances']:
        # Select this instance
        await select_instance(port=instance['port'])
        
        # Trigger slicing
        await slice()
        
        # Export G-code
        project = instance.get('project_name', 'unknown')
        await export_gcode(f"/tmp/{project}.gcode")
```

### Scenario 3: A/B Testing

Compare different slicer settings:

```python
# Instance 1: Settings variant A
await select_instance(port=21987)
await set_config("layer_height", 0.2)
await slice()

# Instance 2: Settings variant B
await select_instance(port=21988)
await set_config("layer_height", 0.15)
await slice()

# Compare results
```

## Troubleshooting

### No Instances Found

**Problem**: `discover_instances()` returns empty list

**Solutions**:
1. Make sure SuperSlicer is running: `ps aux | grep superslicer`
2. Check ConfigServer is enabled: Look for `--enable-config-server` in command line
3. Verify instance registry: `ls -la /tmp/superslicer_instances/`
4. Check process permissions: Ensure temp directory is accessible

### Cannot Connect to Instance

**Problem**: `select_instance()` fails to connect

**Solutions**:
1. Verify instance is still running: Check process ID from instance list
2. Test direct connection: `curl http://localhost:{port}/api/status`
3. Check firewall settings: Ensure ports are not blocked
4. Verify port numbers: Use `netstat -tulpn | grep superslicer`

### Stale Instance Files

**Problem**: Registry shows dead instances

**Solutions**:
- Stale files are automatically cleaned on next instance start
- Manual cleanup: `rm /tmp/superslicer_instances/*.json`
- The `list_instances` API filters out dead processes automatically

## Technical Details

### Instance ID Format

```
{process_id}_{port}
```

Examples:
- `12345_21987` - Process 12345 on port 21987
- `67890_21988` - Process 67890 on port 21988

### Port Auto-Increment

When starting with `--enable-config-server`:

1. Try default port (21987)
2. If in use, try 21988
3. Continue up to 10 attempts
4. Fail if no port available

### Registry File Format

Each instance file (`{instance_id}.json`):

```json
{
  "instance_id": "12345_21987",
  "port": 21987,
  "process_id": 12345,
  "start_time": 1673456789,
  "project_name": "model.3mf"
}
```

## Best Practices

1. **Always discover first**: Call `discover_instances()` before `select_instance()`
2. **Check connection**: Verify `connected` status after selection
3. **Handle errors**: Check `success` field in all responses
4. **Refresh periodically**: Re-discover if instances might have started/stopped
5. **Use instance IDs**: More reliable than port numbers for selection

## Future Enhancements

Potential improvements for future versions:

- [ ] WebSocket notifications for instance changes
- [ ] Instance grouping and tagging
- [ ] Load balancing across instances
- [ ] Synchronized multi-instance operations
- [ ] Instance health monitoring
- [ ] Remote instance support (network discovery)

## Contributing

Found a bug or have a feature request? Please open an issue on the SuperSlicer GitHub repository.

## License

This feature is part of SuperSlicer and follows the same license as the main project.
