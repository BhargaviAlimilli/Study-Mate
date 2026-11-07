"""Read-only MCP client smoke test. Token comes from the process environment, never arguments."""
import asyncio
import json
import os
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from app.core.config import get_settings


async def main():
    token = os.environ.get('STUDYMATE_ACCESS_TOKEN')
    if not token:
        raise SystemExit('Set STUDYMATE_ACCESS_TOKEN to a valid Study Mate JWT in this terminal.')
    url = get_settings().api_public_url.rstrip('/') + '/mcp'
    async with httpx2.AsyncClient(headers={'Authorization': f'Bearer {token}'}) as client:
        async with streamable_http_client(url, http_client=client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                tools = await session.list_tools()
                search = await session.call_tool('search_notes', {'query': 'study concepts', 'k': 2})
                weak = await session.call_tool('get_weak_topics', {})
                print(json.dumps({'tools': [tool.name for tool in tools.tools], 'search_succeeded': not search.is_error,
                    'weak_topics_succeeded': not weak.is_error, 'note': 'Contents and credentials are intentionally omitted.'}, indent=2))
                if search.is_error or weak.is_error:
                    raise SystemExit(1)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        raise SystemExit(f'MCP verification failed ({type(exc).__name__}). Check the API address and token without sharing credentials.') from None
