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


OBSERVE = os.environ.get("MCP_STARTER_OBSERVE") == "1"


class StateError(Exception):
    """상태 파일이 손상돼 읽을 수 없음."""


def load() -> dict:
    if not STATE_PATH.exists():
        return {"steps": {}}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StateError(str(error)) from error
    validate(state)
    return state


def is_time(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate(state) -> None:
    """이 스크립트가 만들 수 있는 형태인지 검사한다. 아니면 StateError."""
    if not isinstance(state, dict) or not isinstance(state.get("steps"), dict):
        raise StateError("steps 항목이 없거나 형식이 다릅니다")
    if set(state) - {"steps", "questions"}:
        raise StateError(f"알 수 없는 항목이 있습니다: {sorted(set(state) - {'steps', 'questions'})}")

    numbers = []
    for key, record in state["steps"].items():
        if not key.isdigit() or int(key) not in STEPS:
            raise StateError(f"단계 번호가 올바르지 않습니다: {key!r}")
        where = f"{key}단계 기록"
        if not isinstance(record, dict) or not record:
            raise StateError(f"{where}이 비었거나 형식이 다릅니다")
        if set(record) - {"start", "end", "skipped"}:
            raise StateError(f"{where}에 알 수 없는 필드가 있습니다: {sorted(set(record) - {'start', 'end', 'skipped'})}")
        if "skipped" in record:
            if record["skipped"] is not True or int(key) not in SKIPPABLE or "end" in record:
                raise StateError(f"{where}의 건너뛰기 표시가 올바르지 않습니다")
        elif "start" not in record:
            raise StateError(f"{where}에 시작 시각이 없습니다")
        for field in ("start", "end"):
            if field in record and not is_time(record[field]):
                raise StateError(f"{where}의 {field} 시각 형식이 다릅니다")
        if "end" in record and record["end"] < record["start"]:
            raise StateError(f"{where}의 완료 시각이 시작보다 앞섭니다")
        numbers.append(int(key))

    numbers.sort()
    if numbers != list(range(len(numbers))):
        raise StateError(f"단계 기록이 0단계부터 이어지지 않습니다: {numbers}")
    for number in numbers[:-1]:
        if not is_done(state["steps"][str(number)]):
            raise StateError(f"{number}단계가 끝나지 않았는데 다음 단계 기록이 있습니다")

    questions = state.get("questions", [])
    if not isinstance(questions, list):
        raise StateError("questions 항목의 형식이 다릅니다")
    for index, question in enumerate(questions):
        where = f"질문 기록 {index + 1}번"
        if not isinstance(question, dict) or set(question) != {"step", "text", "at"}:
            raise StateError(f"{where}의 형식이 다릅니다")
        step = question["step"]
        if step is not None and (isinstance(step, bool) or not isinstance(step, int) or step not in STEPS):
            raise StateError(f"{where}의 단계 번호가 올바르지 않습니다")
        if not isinstance(question["text"], str) or not question["text"].strip():
            raise StateError(f"{where}의 내용이 비었거나 형식이 다릅니다")
        if not is_time(question["at"]):
            raise StateError(f"{where}의 시각 형식이 다릅니다")


def save(state: dict) -> None:
    """임시 파일에 쓴 뒤 교체한다. 쓰는 도중 끊겨도 기존 파일이 깨지지 않는다."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_PATH.with_name(STATE_PATH.name + ".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, STATE_PATH)


def broken_message(reason: str) -> str:
    return (f"진행 상태 파일이 손상돼 읽을 수 없습니다: {STATE_PATH} ({reason}). "
            "자동으로 고치거나 초기화하지 않습니다. 파일 내용을 확인하고, 처음부터 다시 하려면 직접 지워주세요.")


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
        if isinstance(value, str) and re.search(r"(^|[/\\\s'\"();&|])improved([/\\\s'\"();&|]|$)", value.replace("\\", "/")):
            return True
    return False


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}, ensure_ascii=False))


def command_guard(state: dict | None, broken: str | None = None) -> None:
    payload = json.load(sys.stdin)
    if not touches_improved(payload.get("tool_input", {})):
        return
    if broken is not None:
        deny("진행 상태 파일이 손상돼 지금이 몇 단계인지 확인할 수 없어 improved/ 접근을 막았습니다. " + broken_message(broken))
        return
    if reached(state, UNLOCK_IMPROVED_AT):
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


WRITE_COMMANDS = {"start", "complete", "skip", "question"}


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    command = sys.argv[1]
    if OBSERVE and command in WRITE_COMMANDS:
        fail("관찰용 세션(MCP_STARTER_OBSERVE=1)에서는 진행 상태를 바꾸지 않습니다.")
    if OBSERVE and command == "session-context":
        print("[MCP 입문 학습 세트] 이 세션은 관찰용입니다(MCP_STARTER_OBSERVE=1). "
              "tutor 스킬로 학습을 진행하지 말고, 학습자의 질문에만 평소처럼 답하세요. 진행 상태를 바꾸는 명령은 거부됩니다.")
        return
    try:
        state = load()
    except StateError as error:
        if command == "guard":
            command_guard(None, broken=str(error))
        elif command == "session-context":
            print("[MCP 입문 학습 세트] " + broken_message(str(error)))
        else:
            fail(broken_message(str(error)))
        return
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
