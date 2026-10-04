"""개선 버전 server.py가 동작하는지, 그리고 개선 1~5가 실제로 적용됐는지 검증한다.

하나라도 기대와 다르면 어느 항목인지 출력하고 실패(종료 코드 1)로 끝난다.
"""

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

failures = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"  {'✅' if ok else '❌'} {name}: {detail}")
    if not ok:
        failures.append(name)


async def main() -> None:
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"연결 성공 (프로토콜 버전 {session.protocol_version})\n")

            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            resources = (await session.list_resources()).resources
            prompts = {prompt.name: prompt for prompt in (await session.list_prompts()).prompts}

            result = await session.call_tool("list_missions", {})
            missions = result.structured_content["result"]
            check("개선 1 전체 목록 도구", len(missions) == 6, f"list_missions() -> {len(missions)}건 (기대 6)")

            briefing = prompts.get("mission_briefing")
            argument = briefing.arguments[0] if briefing and briefing.arguments else None
            check("개선 2 인자 설명", bool(argument and argument.description), f"{argument.description if argument else '없음'}")
            completion = await session.complete(PromptReference(type="ref/prompt", name="mission_briefing"), {"name": "mission_id", "value": "l"})
            values = completion.completion.values
            check("개선 2 자동완성", sorted(values) == ["ladder", "lotto", "lunch"], f"'l' -> {values}")
            wrong = (await session.get_prompt("mission_briefing", {"mission_id": "스프링"})).messages[0].content.text
            check("개선 2 잘못된 ID 안내", "다시 물어봐" in wrong, wrong[:40] + "...")
            right = (await session.get_prompt("mission_briefing", {"mission_id": "racingcar"})).messages[0].content.text
            check("개선 2 올바른 ID", "자동차 경주" in right, right[:30] + "...")

            mime = resources[0].mime_type if resources else None
            check("개선 3 mime_type", mime == "application/json", f"{mime}")

            titles = {"tool": tools["list_missions"].title, "resource": resources[0].title if resources else None,
                      "prompt": briefing.title if briefing else None}
            check("개선 4 title", all(titles.values()), f"{titles}")

            spring = (await session.call_tool("list_missions", {"course": "스프링"})).structured_content["result"]
            check("개선 5 스프링", len(spring) == 1, f"list_missions('스프링') -> {len(spring)}건 (기대 1)")
            rejected = await session.call_tool("list_missions", {"course": "spring"})
            check("개선 5 잘못된 코스 거절", rejected.is_error, f"list_missions('spring') -> 거절 {rejected.is_error}")

    if failures:
        print(f"\n실패 {len(failures)}건: {', '.join(failures)}")
        sys.exit(1)
    print("\n모두 확인했습니다. (위에 'rejected arguments' 줄이 보이면 개선 5 확인용 정상 기록입니다)")


anyio.run(main)
