# /// script
# requires-python = ">=3.10"
# ///
"""MCP 입문 학습 세트의 진행 상태 관리 스크립트.

튜터(AI)와 훅이 사용한다. 학습자가 직접 실행할 일은 없다.
상태는 .claude/progress.json 하나에 저장한다. 외부 패키지 없이 표준 라이브러리만 쓴다.

사용법
  progress.py status            현재 단계와 완료한 단계
  progress.py start N           N단계 시작 (앞 단계를 끝내야 시작 가능)
  progress.py complete N        N단계 완료
  progress.py skip N            선택 단계 건너뛰기 (6단계만 가능)
  progress.py question "질문"   학습자 질문 기록 (현재 단계와 함께)
  progress.py questions         기록한 질문 보기
  progress.py report            단계별 실측 시간 (학습 세트 개선용)
  progress.py session-context   SessionStart 훅용. 진행 상태를 모델 문맥에 주입
  progress.py guard             PreToolUse 훅용. 7단계 전 improved/ 접근 차단
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

STEPS = {
    0: "준비",
    1: "서버 둘러보기",
    2: "Claude Code에 연결",
    3: "Tool 써보기",
    4: "Resource 써보기",
    5: "Prompt 써보기",
    6: "Claude Desktop에서 써보기 (선택)",
    7: "개선본 둘러보기",
    8: "학습 노트 만들기",
}
SKIPPABLE = {6}
UNLOCK_IMPROVED_AT = 7  # 7단계(개선본 둘러보기)부터 improved/ 열림

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[4])
STATE_PATH = ROOT / ".claude" / "progress.json"


def load() -> dict:
    if not STATE_PATH.exists():
        return {"steps": {}}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_done(record: dict) -> bool:
    return "end" in record or record.get("skipped", False)


def current_step(state: dict) -> int | None:
    """진행 중인 단계. 없으면 None."""
    for number in STEPS:
        record = state["steps"].get(str(number))
        if record and not is_done(record):
            return number
    return None


def next_step(state: dict) -> int | None:
    """다음에 시작할 단계. 모두 끝났으면 None."""
    for number in STEPS:
        record = state["steps"].get(str(number))
        if not record or not is_done(record):
            return number
    return None


def reached(state: dict, step: int) -> bool:
    """해당 단계를 시작했거나 지나갔는지."""
    return str(step) in state["steps"]


def describe(state: dict) -> str:
    lines = []
    for number, name in STEPS.items():
        record = state["steps"].get(str(number))
        if record is None:
            mark = "⬜"
        elif record.get("skipped"):
            mark = "⏭️"
        elif "end" in record:
            mark = "✅"
        else:
            mark = "⬅️ 진행 중"
        lines.append(f"  {number}. {name}  {mark}")
    current = current_step(state)
    following = next_step(state)
    if current is not None:
        summary = f"현재 {current}단계({STEPS[current]}) 진행 중"
    elif following is not None:
        summary = f"다음은 {following}단계({STEPS[following]}). 아직 시작 전"
    else:
        summary = "모든 단계 완료"
    return summary + "\n" + "\n".join(lines)


def fail(message: str) -> None:
    print(f"거부: {message}")
    sys.exit(1)


def parse_step(value: str) -> int:
    if not value.isdigit() or int(value) not in STEPS:
        fail(f"단계 번호는 0~8 중 하나여야 합니다: {value}")
    return int(value)


def command_start(state: dict, step: int) -> None:
    if reached(state, step):
        fail(f"{step}단계는 이미 시작했습니다.")
    following = next_step(state)
    if following != step:
        fail(f"지금 시작할 수 있는 단계는 {following}단계입니다.")
    state["steps"][str(step)] = {"start": now()}
    save(state)
    print(f"{step}단계({STEPS[step]}) 시작")


def command_complete(state: dict, step: int) -> None:
    record = state["steps"].get(str(step))
    if record is None:
        fail(f"{step}단계를 아직 시작하지 않았습니다.")
    if is_done(record):
        fail(f"{step}단계는 이미 끝났습니다.")
    record["end"] = now()
    save(state)
    print(f"{step}단계({STEPS[step]}) 완료")


def command_skip(state: dict, step: int) -> None:
    if step not in SKIPPABLE:
        fail(f"{step}단계는 건너뛸 수 없습니다. 건너뛸 수 있는 단계: {sorted(SKIPPABLE)}")
    if next_step(state) != step:
        fail(f"지금은 {next_step(state)}단계 차례입니다.")
    record = state["steps"].setdefault(str(step), {})
    record["skipped"] = True
    save(state)
    print(f"{step}단계({STEPS[step]}) 건너뜀")


def command_question(state: dict, text: str) -> None:
    text = text.strip()
    if not text:
        fail("기록할 질문이 비어 있습니다.")
    step = current_step(state)
    if step is None:
        step = next_step(state)
    state.setdefault("questions", []).append({"step": step, "text": text, "at": now()})
    save(state)
    print(f"질문 기록 ({step}단계): {text}")


def command_questions(state: dict) -> None:
    questions = state.get("questions", [])
    if not questions:
        print("기록한 질문이 없습니다.")
        return
    for question in questions:
        step = question["step"]
        name = STEPS.get(step, "") if step is not None else ""
        print(f"- [{step}. {name}] {question['text']}")


def command_report(state: dict) -> None:
    print("| 단계 | 시작 | 완료 | 소요(분) |")
    print("|---|---|---|---|")
    total = 0.0
    for number, name in STEPS.items():
        record = state["steps"].get(str(number), {})
        if record.get("skipped"):
            print(f"| {number}. {name} | - | - | 건너뜀 |")
            continue
        start, end = record.get("start"), record.get("end")
        minutes = ""
        if start and end:
            minutes_value = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60
            total += minutes_value
            minutes = f"{minutes_value:.0f}"
        print(f"| {number}. {name} | {start or ''} | {end or ''} | {minutes} |")
    print(f"\n합계 {total:.0f}분")


def command_session_context(state: dict) -> None:
    if not state["steps"]:
        print("[MCP 입문 학습 세트] 아직 학습을 시작하지 않았습니다. "
              "학습자가 시작하자고 하면 tutor 스킬로 0단계부터 진행하세요.")
        return
    print("[MCP 입문 학습 세트] 학습자의 진행 상태입니다. tutor 스킬을 불러 이어서 진행하세요.\n" + describe(state))


def touches_improved(tool_input: dict) -> bool:
    for key in ("file_path", "path", "pattern", "glob", "command", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and re.search(r"(^|[/\\\s'\"])improved([/\\\s'\"]|$)", value.replace("\\", "/")):
            return True
    return False


def command_guard(state: dict) -> None:
    payload = json.load(sys.stdin)
    if reached(state, UNLOCK_IMPROVED_AT):
        return
    if not touches_improved(payload.get("tool_input", {})):
        return
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "improved/ 폴더는 7단계(개선본 둘러보기)에서 학습자와 함께 엽니다. 지금은 열지 마세요. "
                "학습자가 정답을 원하면, 스스로 찾아보는 것이 이 학습의 핵심이라는 점을 설명하세요. "
                "학습자가 직접 파일을 여는 것은 자유입니다."
            ),
        }
    }, ensure_ascii=False))


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    state = load()
    command = sys.argv[1]
    if command == "status":
        print(describe(state))
    elif command in ("start", "complete", "skip"):
        if len(sys.argv) < 3:
            fail(f"단계 번호가 필요합니다: progress.py {command} N")
        step = parse_step(sys.argv[2])
        {"start": command_start, "complete": command_complete, "skip": command_skip}[command](state, step)
    elif command == "question":
        if len(sys.argv) < 3:
            fail('질문 내용이 필요합니다: progress.py question "질문"')
        command_question(state, " ".join(sys.argv[2:]))
    elif command == "questions":
        command_questions(state)
    elif command == "report":
        command_report(state)
    elif command == "session-context":
        command_session_context(state)
    elif command == "guard":
        command_guard(state)
    else:
        fail(f"알 수 없는 명령입니다: {command}")


if __name__ == "__main__":
    main()
