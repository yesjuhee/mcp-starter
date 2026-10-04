"""개선 버전 server.py가 정상 동작하는지, 그리고 개선 사항이 실제로 적용됐는지 확인한다."""

import sys
from pathlib import Path

import anyio
from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import PromptReference

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
                print(f"  {tool.name} ({tool.title}): {tool.description}")
                print(f"    입력 스키마: {tool.input_schema['properties']}")

            resources = await session.list_resources()
            print("[Resources]")
            for resource in resources.resources:
                print(f"  {resource.uri} ({resource.title}) mime_type={resource.mime_type}")

            prompts = await session.list_prompts()
            print("[Prompts]")
            for prompt in prompts.prompts:
                arguments = [(argument.name, argument.description) for argument in prompt.arguments or []]
                print(f"  {prompt.name} ({prompt.title}) 인자={arguments}")

            print("\n[개선 사항 확인]")
            result = await session.call_tool("list_missions", {})
            print(f"  개선 1  list_missions() -> 전체 {len(result.structured_content['result'])}건")

            result = await session.call_tool("list_missions", {"course": "스프링"})
            print(f"  개선 5  list_missions('스프링') -> {len(result.structured_content['result'])}건")

            result = await session.call_tool("list_missions", {"course": "spring"})
            print(f"  개선 5  list_missions('spring') -> 에러로 거절됨: {result.is_error}")

            completion = await session.complete(PromptReference(type="ref/prompt", name="mission_briefing"), {"name": "mission_id", "value": "l"})
            print(f"  개선 2  자동완성('l') -> {completion.completion.values}")

            prompt = await session.get_prompt("mission_briefing", {"mission_id": "스프링"})
            print(f"  개선 2  잘못된 미션 ID -> {prompt.messages[0].content.text[:44]}...")

            prompt = await session.get_prompt("mission_briefing", {"mission_id": "racingcar"})
            print(f"  개선 2  올바른 미션 ID -> {prompt.messages[0].content.text[:34]}...")

    print("\n모두 확인했습니다.")


anyio.run(main)
