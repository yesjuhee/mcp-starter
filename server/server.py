"""MCP 입문 학습용 hello 서버.

Tool, Resource, Prompt를 하나씩 가진 가장 작은 MCP 서버다.
서버가 호출될 때마다 calls.log에 한 줄씩 기록을 남긴다.
이 기록을 보면서 "누가, 언제, 무엇을 불렀는지" 관찰하는 것이 이 학습의 핵심이다.

이 서버는 잘 동작한다. 하지만 일부러 고치지 않은 부분이 몇 군데 있다.
직접 써보면서 찾아보자. 개선한 버전은 ../improved/에 있다.
"""

import json
from datetime import datetime
from pathlib import Path

from mcp.server import MCPServer

LOG_PATH = Path(__file__).parent / "calls.log"

# 초록스터디 미션 목록. 미션 이름은 실제이고, top_topic은 학습용 예시 데이터다.
MISSIONS = {
    "calculator": {"name": "계산기", "course": "자바", "top_topic": "단위 테스트"},
    "racingcar": {"name": "자동차 경주", "course": "자바", "top_topic": "난수와 테스트 용이성"},
    "lotto": {"name": "로또", "course": "자바", "top_topic": "원시값 포장"},
    "ladder": {"name": "사다리", "course": "자바", "top_topic": "함수형 프로그래밍"},
    "roomescape": {"name": "방탈출", "course": "스프링", "top_topic": "레이어드 아키텍처"},
    "lunch": {"name": "점심 뭐 먹지", "course": "리액트", "top_topic": "상태 관리"},
}

mcp = MCPServer(name="cholog-hello")


def log(kind: str, name: str, args: dict) -> None:
    """호출 기록을 calls.log에 남긴다."""
    line = f"{datetime.now():%H:%M:%S}  {kind:<8} {name}  {json.dumps(args, ensure_ascii=False)}\n"
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)


# Tool: AI 모델이 대화 중에 스스로 판단해서 호출하는 함수.
# docstring이 그대로 도구 설명이 되고, 타입 힌트가 그대로 입력 스키마가 된다.
@mcp.tool()
def find_missions(keyword: str) -> list[dict]:
    """이름이나 코스에 키워드가 포함된 초록스터디 미션을 찾는다."""
    log("TOOL", "find_missions", {"keyword": keyword})
    return [
        {"id": mission_id, **mission}
        for mission_id, mission in MISSIONS.items()
        if keyword in mission["name"] or keyword in mission["course"]
    ]


# Resource: URI로 식별되는 읽을 수 있는 데이터.
# 사용자가 첨부할 수도 있고, 호스트가 허용하면 모델이 읽을 수도 있다.
@mcp.resource("cholog://missions", description="초록스터디 전체 미션 목록")
def all_missions() -> str:
    log("RESOURCE", "cholog://missions", {})
    return json.dumps(MISSIONS, ensure_ascii=False, indent=2)


# Prompt: 사용자가 메뉴에서 골라 쓰는 질문 템플릿.
@mcp.prompt()
def mission_briefing(mission_id: str) -> str:
    """스터디 리드가 미션 시작 전에 참고할 브리핑을 요청한다."""
    log("PROMPT", "mission_briefing", {"mission_id": mission_id})
    return (
        f"초록스터디 '{mission_id}' 미션을 곧 시작해. "
        "스터디 리드 입장에서 미리 짚어줄 포인트를 3개만 정리해줘. "
        "필요하면 find_missions 도구를 써."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
