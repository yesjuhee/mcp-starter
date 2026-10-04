"""MCP 입문 학습용 hello 서버의 개선 버전.

../server/server.py를 직접 써보며 발견할 수 있는 문제 5가지를 고친 버전이다.
고친 곳마다 "개선 N" 주석을 달았다. 정답이 하나뿐인 것은 아니니 자신의 방식과 비교해보자.

  개선 1. "전체 목록"을 위한 도구가 없어서, 모델이 keyword=""로 우회했다
  개선 2. Prompt 인자에 안내와 검증이 없어서, 아무 값이나 들어갔다
  개선 3. Resource에 mime_type이 없어서, JSON인데 텍스트로 취급됐다
  개선 4. title이 없어서, 메뉴에 함수 이름(All missions 등)이 그대로 보였다
  개선 5. 코스를 자유 문자열로 받아서, "spring" 같은 값이 들어오면 빈 결과가 나왔다
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from mcp.server import MCPServer
from mcp.types import Completion, PromptReference

LOG_PATH = Path(__file__).parent / "calls.log"

MISSIONS = {
    "calculator": {"name": "계산기", "course": "자바", "top_topic": "단위 테스트"},
    "racingcar": {"name": "자동차 경주", "course": "자바", "top_topic": "난수와 테스트 용이성"},
    "lotto": {"name": "로또", "course": "자바", "top_topic": "원시값 포장"},
    "ladder": {"name": "사다리", "course": "자바", "top_topic": "함수형 프로그래밍"},
    "roomescape": {"name": "방탈출", "course": "스프링", "top_topic": "레이어드 아키텍처"},
    "lunch": {"name": "점심 뭐 먹지", "course": "리액트", "top_topic": "상태 관리"},
}

# 개선 5: 코스는 정해진 값 중에서만 고르게 한다. 입력 스키마에 선택지로 노출된다.
Course = Literal["자바", "스프링", "리액트"]

mcp = MCPServer(name="cholog-hello")


def log(kind: str, name: str, args: dict) -> None:
    """호출 기록을 calls.log에 남긴다."""
    line = f"{datetime.now():%H:%M:%S}  {kind:<8} {name}  {json.dumps(args, ensure_ascii=False)}\n"
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)


# 개선 1: "전체 목록"과 "코스별 목록"을 명시적인 도구로 제공한다.
#         모델이 빈 문자열 같은 우회로를 찾을 필요가 없다.
# 개선 4: title로 사람이 읽을 이름을 준다.
@mcp.tool(title="미션 목록 조회")
def list_missions(
    course: Annotated[Course | None, Field(description="코스로 거르려면 지정한다. 생략하면 전체 미션을 돌려준다.")] = None,
) -> list[dict]:
    """초록스터디 미션 목록을 돌려준다. 전체 목록이 필요하면 course를 생략한다."""
    log("TOOL", "list_missions", {"course": course})
    return [
        {"id": mission_id, **mission}
        for mission_id, mission in MISSIONS.items()
        if course is None or mission["course"] == course
    ]


# 개선 3: 내용이 JSON이라는 것을 mime_type으로 알린다.
# 개선 4: title로 메뉴에 보일 이름을 준다.
@mcp.resource(
    "cholog://missions",
    title="초록스터디 전체 미션 목록",
    description="초록스터디 전체 미션 목록 (JSON)",
    mime_type="application/json",
)
def all_missions() -> str:
    log("RESOURCE", "cholog://missions", {})
    return json.dumps(MISSIONS, ensure_ascii=False, indent=2)


# 개선 2: 인자에 설명을 달고, 잘못된 값이 들어오면 모델이 사용자에게 다시 묻게 한다.
#         예외를 던지면 안내 문구가 "Error rendering prompt ..."라는 일반 메시지로 덮여서
#         사용자에게 전달되지 않는다. 그래서 거절 대신 "다시 물어봐" 문장을 돌려준다.
# 개선 4: title로 메뉴에 보일 이름을 준다.
@mcp.prompt(title="미션 시작 전 브리핑")
def mission_briefing(
    mission_id: Annotated[str, Field(description=f"미션 ID. 다음 중 하나: {', '.join(MISSIONS)}")],
) -> str:
    """스터디 리드가 미션 시작 전에 참고할 브리핑을 요청한다."""
    log("PROMPT", "mission_briefing", {"mission_id": mission_id})
    if mission_id not in MISSIONS:
        return (
            f"초록스터디 미션 브리핑을 받고 싶은데, 미션 ID를 '{mission_id}'라고 잘못 입력했어. "
            f"가능한 미션 ID는 {', '.join(MISSIONS)}야. 어떤 미션인지 나에게 다시 물어봐줘."
        )
    mission = MISSIONS[mission_id]
    return (
        f"초록스터디 '{mission['name']}'({mission['course']}) 미션을 곧 시작해. "
        "스터디 리드 입장에서 미리 짚어줄 포인트를 3개만 정리해줘. "
        "필요하면 list_missions 도구를 써."
    )


# 개선 2: Prompt 인자를 입력할 때 자동완성 후보를 제공한다.
#         호스트가 자동완성을 지원하면, 입력 중에 미션 ID 목록이 뜬다.
@mcp.completion()
async def complete_argument(ref, argument, context):
    if isinstance(ref, PromptReference) and ref.name == "mission_briefing" and argument.name == "mission_id":
        candidates = [mission_id for mission_id in MISSIONS if mission_id.startswith(argument.value)]
        return Completion(values=candidates)
    return None


if __name__ == "__main__":
    mcp.run(transport="stdio")
