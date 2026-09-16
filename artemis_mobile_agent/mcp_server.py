from __future__ import annotations
from .mcp_tools import mobile_diagnose, mobile_get_device_state, mobile_inspect_trace, mobile_manage_task, mobile_run_task

def main():
    try:
        from mcp.server import MCPServer
    except ImportError as e:
        raise SystemExit("Install MCP support with: pip install 'artemis-mobile-agent[mcp]'") from e
    mcp = MCPServer("artemis-mobile-agent")
    for fn in [mobile_run_task, mobile_manage_task, mobile_get_device_state, mobile_inspect_trace, mobile_diagnose]:
        mcp.tool()(fn)
    mcp.run()

if __name__ == "__main__":
    main()
