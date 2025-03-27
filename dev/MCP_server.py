from mcp.server.fastmcp import FastMCP

"""
The FastMCP Server manages connections, follows the MCP protocol, and routes messages. Tools help the server perform operations. The Resource provides messages.
"""


# instantiate an MCP server client
mcp = FastMCP("Hello World")


# TOOLS: use @mcp.tool()
@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


# RESOURCE: use @mcp.resource()
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Add a dynamic greeting resource. Gets a personalized greeting"""
    return f"Hello, {name}!"


# We start the MCP server using @mcp.run()
if __name__ == "__main__":
    mcp.run(transport="stdio")  # comms via standard input/output (stdio)
