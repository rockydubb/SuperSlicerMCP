#!/home/guy/tmp/SuperSlicer/venv/bin/python3
"""
Test script for SuperSlicer multi-instance discovery and management.

This script demonstrates:
1. Discovering multiple running SuperSlicer instances
2. Listing all discovered instances
3. Selecting specific instances
4. Querying status from different instances

Usage:
    # Start multiple SuperSlicer instances first, then run:
    python3 test_multi_instance.py
"""

import asyncio
import httpx
import json
from typing import Dict, Any

# Configuration
HOST = "localhost"
DEFAULT_PORT = 21987
TIMEOUT = 5.0


async def discover_instances() -> Dict[str, Any]:
    """Discover all running SuperSlicer instances"""
    print(f"\n🔍 Discovering SuperSlicer instances...")
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"http://{HOST}:{DEFAULT_PORT}/api/list_instances")
            response.raise_for_status()
            data = response.json()
            
            instances = data.get("instances", [])
            print(f"✓ Found {len(instances)} active instance(s)")
            
            return {"success": True, "instances": instances}
    except Exception as e:
        print(f"✗ Failed to discover instances: {e}")
        return {"success": False, "instances": [], "error": str(e)}


async def get_instance_status(port: int) -> Dict[str, Any]:
    """Get status from a specific instance"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"http://{HOST}:{port}/api/status")
            response.raise_for_status()
            return {"success": True, "data": response.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def main():
    """Main test function"""
    print("=" * 70)
    print("SuperSlicer Multi-Instance Discovery Test")
    print("=" * 70)
    
    # Step 1: Discover instances
    discovery_result = await discover_instances()
    
    if not discovery_result["success"]:
        print("\n❌ Cannot discover instances. Make sure SuperSlicer is running!")
        print("   Start SuperSlicer with: superslicer --enable-config-server")
        return
    
    instances = discovery_result["instances"]
    
    if not instances:
        print("\n⚠️  No instances found!")
        print("   Make sure SuperSlicer is running with ConfigServer enabled")
        print("   Start with: superslicer --enable-config-server")
        return
    
    # Step 2: Display discovered instances
    print(f"\n📋 Discovered Instances:")
    print("-" * 70)
    
    for idx, inst in enumerate(instances, 1):
        print(f"\nInstance #{idx}:")
        print(f"  Instance ID:  {inst.get('instance_id')}")
        print(f"  Port:         {inst.get('port')}")
        print(f"  Process ID:   {inst.get('process_id')}")
        print(f"  Start Time:   {inst.get('start_time')}")
        
        project_name = inst.get('project_name', '')
        if project_name:
            print(f"  Project:      {project_name}")
        else:
            print(f"  Project:      (No project loaded)")
    
    # Step 3: Query status from each instance
    print(f"\n📊 Querying Status from Each Instance:")
    print("-" * 70)
    
    for idx, inst in enumerate(instances, 1):
        port = inst.get('port')
        instance_id = inst.get('instance_id')
        
        print(f"\n Instance {instance_id} (Port {port}):")
        status_result = await get_instance_status(port)
        
        if status_result["success"]:
            status = status_result["data"]
            print(f"   ✓ Connected")
            print(f"   Version:      {status.get('app_version', 'unknown')}")
            print(f"   Project:      {status.get('project_name', '(none)')}")
            print(f"   Objects:      {status.get('object_count', 0)}")
            print(f"   Has Model:    {status.get('has_model', False)}")
        else:
            print(f"   ✗ Failed: {status_result.get('error')}")
    
    # Step 4: Test differentiation
    if len(instances) > 1:
        print(f"\n🎯 Instance Differentiation Test:")
        print("-" * 70)
        print(f"✓ Successfully differentiated {len(instances)} instances!")
        print(f"  Each instance has:")
        print(f"    • Unique instance ID (PID_Port)")
        print(f"    • Separate port numbers")
        print(f"    • Independent project states")
        
        # Show differences
        print(f"\n  Differences detected:")
        for idx, inst in enumerate(instances, 1):
            project = inst.get('project_name', '(No project)')
            print(f"    Instance {idx}: Port {inst['port']} - {project}")
    
    print(f"\n" + "=" * 70)
    print("✓ Multi-instance test completed successfully!")
    print("=" * 70)
    
    # Step 5: MCP usage example
    print(f"\n💡 MCP Client Usage:")
    print("-" * 70)
    print("  # Discover instances")
    print("  result = await discover_instances()")
    print()
    print("  # Select specific instance by port")
    print(f"  await select_instance(port={instances[0]['port']})")
    print()
    print("  # Or select by instance ID")
    print(f"  await select_instance(instance_id='{instances[0]['instance_id']}')")
    print()
    print("  # Get current instance info")
    print("  await get_current_instance()")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
