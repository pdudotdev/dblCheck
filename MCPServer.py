# dblCheck - Network Intent Validation Tool
"""
dblCheck MCP Server — read-only tool registration entry point.

Read-only tools only. No push_config, no approval workflow, no Jira.

  transport/   — SSH + RESTCONF transports
  tools/       — MCP tool handler functions
  core/        — inventory, settings, logging
"""
import logging
from fastmcp import FastMCP

from core.logging_config import setup_logging

setup_logging()
log = logging.getLogger("dblcheck")

from tools.protocol    import get_ospf, get_bgp
from tools.routing     import get_routing, get_routing_policies
from tools.operational import get_interfaces, ping, traceroute, run_show
from tools.state       import get_intent


mcp = FastMCP("dblcheck")

mcp.tool(name="get_ospf")(get_ospf)
mcp.tool(name="get_bgp")(get_bgp)
mcp.tool(name="get_routing")(get_routing)
mcp.tool(name="get_routing_policies")(get_routing_policies)
mcp.tool(name="get_interfaces")(get_interfaces)
mcp.tool(name="ping")(ping)
mcp.tool(name="traceroute")(traceroute)
mcp.tool(name="run_show")(run_show)
mcp.tool(name="get_intent")(get_intent)

log.info("dblCheck MCP Server started — 9 read-only tools registered")

if __name__ == "__main__":
    mcp.run()
