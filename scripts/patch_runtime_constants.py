"""Patch baked-in constants in the answer-engine bytecode.

The `services/ai_agent_service_runtime.pyc` module is bytecode-only (no source).
Two constants inside it cannot be changed any other way:

  * temperature 0.35 -> 0.1   on the property/factual generation call
    (build_ai_support_answer, stream_ai_support_answer_events)
  * agent_mode "gemini" -> "remote_llm"   in the result dict of the same two
    functions. "remote_llm" is the value services/observability.normalize_agent_mode
    already maps "gemini" to, and a valid AGENT_MODE_ENUM member.

This never writes the original .pyc. It emits `<name>.patched.pyc` next to it;
the loader in services/ai_agent_service.py picks that up in preference. Re-run
after replacing the original, or delete the .patched.pyc to revert.

Usage:  .venv/Scripts/python.exe scripts/patch_runtime_constants.py
"""
from __future__ import annotations

import marshal
import sys
import types
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "services" / "ai_agent_service_runtime.pyc"
OUT = SRC.with_suffix(".patched.pyc")
TARGET_FUNCS = {"build_ai_support_answer", "stream_ai_support_answer_events"}
CONST_MAP = {0.35: 0.1, "gemini": "remote_llm"}
EXPECTED = {
    ("<module>.build_ai_support_answer", 0.35, 0.1),
    ("<module>.build_ai_support_answer", "gemini", "remote_llm"),
    ("<module>.stream_ai_support_answer_events", 0.35, 0.1),
    ("<module>.stream_ai_support_answer_events", "gemini", "remote_llm"),
}


def _patch_consts(consts):
    out, changed = [], []
    for c in consts:
        for old, new in CONST_MAP.items():
            if type(c) is type(old) and c == old:
                out.append(new)
                changed.append((old, new))
                break
        else:
            out.append(c)
    return tuple(out), changed


def _walk(code, path="<module>"):
    new_consts, report = [], []
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            child, child_report = _walk(c, f"{path}.{c.co_name}")
            new_consts.append(child)
            report += child_report
        else:
            new_consts.append(c)
    if code.co_name in TARGET_FUNCS:
        patched, changed = _patch_consts(new_consts)
        if changed:
            report += [(path, old, new) for old, new in changed]
            return code.replace(co_consts=patched), report
    if any(isinstance(x, types.CodeType) for x in code.co_consts):
        return code.replace(co_consts=tuple(new_consts)), report
    return code, report


def _scan_targets(code):
    hits = []
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            hits += _scan_targets(c)
    if code.co_name in TARGET_FUNCS:
        hits += [(code.co_name, repr(c)) for c in code.co_consts if c == 0.35 or c == "gemini"]
    return hits


def main() -> None:
    raw = SRC.read_bytes()
    header, body = raw[:16], raw[16:]
    patched, report = _walk(marshal.loads(body))

    if set(report) != EXPECTED:
        sys.exit(f"unexpected patch set:\n  missing {EXPECTED - set(report)}\n  extra {set(report) - EXPECTED}")

    print("Patched constants:")
    for path, old, new in report:
        print(f"  {path}: {old!r} -> {new!r}")

    OUT.write_bytes(header + marshal.dumps(patched))
    print(f"\nWrote {OUT.name} ({OUT.stat().st_size} bytes; original {SRC.stat().st_size}, untouched)")

    leftovers = _scan_targets(marshal.loads(OUT.read_bytes()[16:]))
    if leftovers:
        sys.exit(f"verification failed, stale constants remain: {leftovers}")
    print("Verified: no 0.35 / 'gemini' constants remain in the two target functions.")


if __name__ == "__main__":
    main()
