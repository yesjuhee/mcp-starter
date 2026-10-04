"""server.py가 정상 동작하는지 확인한다.

AI 호스트(Claude Code 등)에 연결하기 전에, 파이썬 MCP 클라이언트로 직접 붙어서
Tool, Resource, Prompt 목록을 조회하고 하나씩 호출해본다.
"""

import sys
from pathlib import Path

import anyio
from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER = StdioServerParameters(
    command=sys.executable,
    args=[str(Path(__file__).parent / "server.py")],
)


async def main() -> None:
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"연결 성공 (프로토콜 버전 {session.protocol_version})\n")

            tools = await session.list_tools()
            print("[Tools]")
            for tool in tools.tools:
                print(f"  {tool.name}: {tool.description}")

            resources = await session.list_resources()
            print("[Resources]")
            for resource in resources.resources:
                print(f"  {resource.uri}: {resource.description}")

            prompts = await session.list_prompts()
            print("[Prompts]")
            for prompt in prompts.prompts:
                arguments = [argument.name for argument in prompt.arguments or []]
                print(f"  {prompt.name}: {prompt.description}  인자={arguments}")

            print("\n[호출해보기]")
            result = await session.call_tool("find_missions", {"keyword": "자바"})
            print(f"  find_missions('자바') -> 결과 {len(result.content)}건")

            resource = await session.read_resource("cholog://missions")
            print(f"  cholog://missions -> {len(resource.contents[0].text)}자")

            prompt = await session.get_prompt("mission_briefing", {"mission_id": "racingcar"})
            print(f"  mission_briefing('racingcar') -> {prompt.messages[0].content.text[:30]}...")

    print("\n모두 정상입니다. calls.log에 기록이 3줄 생겼는지 확인해보세요.")


anyio.run(main)
