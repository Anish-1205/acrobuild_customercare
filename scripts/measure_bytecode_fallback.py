"""Measure how often traffic reaches the un-reconstructed answer-engine bytecode.

Runs the committed 200-prompt corpus (scripts/eval_prompts.json) through
`run_support_orchestration` in-process, with the LLM call stubbed (no RunPod
traffic), and tallies the `bytecode_fallback` telemetry events per turn:

  - legacy_bytecode_invoked  -> reached `_legacy_build_company_api_direct_answer`
  - raw_document_dump_path    -> `should_return_verbatim_source_answer` returned true
  - generic_fallback_answer   -> `build_fallback_assist_answer` fired

Also classifies the final answer text (belt-and-braces on the dump detection).

Run:  .venv/Scripts/python.exe scripts/measure_bytecode_fallback.py
"""
from __future__ import annotations

import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "scripts" / "eval_prompts.json"
sys.path.insert(0, str(ROOT))

# --- stub the LLM before importing the graph ------------------------------
import qwen  # noqa: E402

qwen.generate_qwen_chat_response = lambda **kw: "STUBBED_LLM_ANSWER about the project."
qwen.stream_qwen_chat_response = lambda **kw: iter(["STUBBED_LLM_ANSWER about the project."])

from graph.main_orchestrator import run_support_orchestration  # noqa: E402

DUMP_MARKERS = (
    "here is the relevant information:",
    "here is what i found:",
    "i have linked the closest support content",
)


class _Tap(logging.Handler):
    def __init__(self):
        super().__init__()
        self.events: list[str] = []

    def emit(self, record):
        m = re.search(r"event=(\w+)", record.getMessage())
        if m:
            self.events.append(m.group(1))


def main() -> None:
    tap = _Tap()
    logging.getLogger("bytecode_fallback").addHandler(tap)
    logging.getLogger("bytecode_fallback").setLevel(logging.INFO)

    cases = json.loads(PROMPTS.read_text(encoding="utf-8"))
    per_turn = []

    for case in cases:
        prompt = case["prompt"]
        follow = re.match(r"Previous:\s*(.*?)\s*Current:\s*(.*)", prompt, flags=re.IGNORECASE)
        history: list[dict] = []
        if follow:
            prev, prompt = follow.group(1).strip(), follow.group(2).strip()
            try:
                prev_ans = run_support_orchestration(
                    issue=prev, conversation_id=f"m{case['id']}", conversation_messages=history,
                    prefer_qwen_response=True,
                ).get("answer", "")
            except Exception as exc:  # noqa: BLE001
                prev_ans = f"(error: {exc})"
            history = [{"sender": "customer", "text": prev}, {"sender": "bot", "text": prev_ans}]

        tap.events.clear()
        try:
            payload = run_support_orchestration(
                issue=prompt, conversation_id=f"m{case['id']}", conversation_messages=history,
                prefer_qwen_response=True,
            )
            answer = str(payload.get("answer", "") or "")
        except Exception as exc:  # noqa: BLE001
            answer = f"(error: {exc})"

        ev = set(tap.events)
        answer_is_dump = any(marker in answer.lower() for marker in DUMP_MARKERS)
        per_turn.append({
            "id": case["id"], "category": case["category"], "prompt": prompt,
            "reached_bytecode": "legacy_bytecode_invoked" in ev,
            "dump_path_chosen": "raw_document_dump_path" in ev,
            "generic_fallback": "generic_fallback_answer" in ev,
            "answer_is_dump": answer_is_dump,
            "answer_preview": answer[:120],
        })

    total = len(per_turn)
    reached = [t for t in per_turn if t["reached_bytecode"]]
    dumps = [t for t in per_turn if t["answer_is_dump"] or t["dump_path_chosen"]]
    generic = [t for t in per_turn if t["generic_fallback"]]

    print(f"corpus: {total} prompts (scripts/eval_prompts.json), LLM stubbed\n")
    print(f"reached the bytecode legacy fn : {len(reached):3d} / {total}  ({100*len(reached)/total:.0f}%)")
    print(f"raw-document-dump answer       : {len(dumps):3d} / {total}  ({100*len(dumps)/total:.0f}%)")
    print(f"generic fallback-assist answer : {len(generic):3d} / {total}  ({100*len(generic)/total:.0f}%)")
    caught = total - len(reached) - len(generic)
    print(f"handled before the bytecode fn : ~{caught} / {total}\n")

    print("dump answers by category:", dict(Counter(t["category"] for t in dumps)))
    print("bytecode-reached by category:", dict(Counter(t["category"] for t in reached)))

    out = ROOT / "scripts" / "_bytecode_fallback_measure.json"
    out.write_text(json.dumps(per_turn, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nper-turn detail -> {out.relative_to(ROOT)}")
    print("\nsample dump answers:")
    for t in dumps[:12]:
        print(f"  [{t['id']:>3}] {t['category']:<18} {t['prompt'][:50]!r} -> {t['answer_preview']!r}")


if __name__ == "__main__":
    main()
