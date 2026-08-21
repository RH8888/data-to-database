#!/usr/bin/env python3
"""Conservative Telegram course/session extractor.

Pairs an explicit course header message with the next content-bearing message only.
Messages with URLs but no nearby explicit header are emitted as ambiguous standalone
courses instead of being merged into the previous course.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

URL_RE = re.compile(r"https?://[^\s)\]}>'\"،]+")
SESSION_RE = re.compile(r"(?m)^\s*\.?\s*((?:جلسه|بخش)\s*[۰-۹0-9]+(?:\s*[-/–—]\s*[^\n]+)?)")
HEADER_SUBJECT_RE = re.compile(r"کلاس(?:\s*های|‌های)?\s+(.+?)\s*💎")
HEADER_TEACHER_RE = re.compile(r"✔️\s*([^\n]+)")
HEADER_PROGRAM_RE = re.compile(r"⬅️\s*([^\n]+)")
NOISE_RE = re.compile(r"^[.\s〰️⚜️✈️@Stream_Konkur@StreamClass]+$")


@dataclass
class Header:
    message_id: int
    raw_title: str
    subject: str | None
    teacher: str | None
    program: str | None


def text_of(message: dict[str, Any]) -> str:
    text = message.get("text", "")
    if isinstance(text, list):
        return "".join(part if isinstance(part, str) else part.get("text", "") for part in text)
    return str(text)


def compact(text: str) -> str:
    return " ".join(line.strip() for line in text.splitlines() if line.strip())


def is_noise(text: str) -> bool:
    return not text.strip() or bool(NOISE_RE.fullmatch(text.strip()))


def parse_header(message: dict[str, Any]) -> Header | None:
    text = text_of(message)
    if "💎" not in text or "✔️" not in text or "⬅️" not in text:
        return None
    subject = HEADER_SUBJECT_RE.search(text)
    teacher = HEADER_TEACHER_RE.search(text)
    program = HEADER_PROGRAM_RE.search(text)
    return Header(
        message_id=message["id"],
        raw_title=compact(text),
        subject=subject.group(1).strip() if subject else None,
        teacher=teacher.group(1).strip() if teacher else None,
        program=program.group(1).strip() if program else None,
    )


def domains(urls: list[str]) -> list[str]:
    out = []
    for url in urls:
        host = re.sub(r"^https?://", "", url).split("/", 1)[0].lower()
        if host not in out:
            out.append(host)
    return out


def parse_sessions(text: str, urls: list[str]) -> list[dict[str, Any]]:
    matches = list(SESSION_RE.finditer(text))
    if not matches:
        return [{"heading": None, "session_number": None, "urls": urls}]
    sessions = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end]
        heading = match.group(1).strip()
        num = re.search(r"[۰-۹0-9]+", heading)
        chunk_urls = URL_RE.findall(chunk)
        sessions.append({"heading": heading, "session_number": num.group(0) if num else None, "urls": chunk_urls})
    return sessions


def title_from_content(text: str) -> str | None:
    first = next((line.strip(" .") for line in text.splitlines() if line.strip() and not URL_RE.match(line.strip())), "")
    if first and not first.startswith(("جلسه", "بخش")) and len(first) > 3:
        return first
    return None


def extract(input_path: Path) -> dict[str, Any]:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    messages = [m for m in data.get("messages", []) if m.get("type") == "message"]
    courses = []
    ambiguities = []
    duplicate_locations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pending: Header | None = None

    for message in messages:
        mid = message.get("id")
        text = text_of(message)
        header = parse_header(message)
        if header:
            if pending:
                ambiguities.append({"message_id": pending.message_id, "reason": "explicit header was not followed by URL content"})
            pending = header
            continue
        urls = URL_RE.findall(text)
        if not urls:
            if not is_noise(text) and pending:
                ambiguities.append({"message_id": mid, "pending_header_id": pending.message_id, "reason": "non-url message between header and content"})
                pending = None
            continue

        explicit_title = title_from_content(text)
        if pending:
            raw_title = explicit_title or pending.raw_title
            course = {**asdict(pending), "raw_title": raw_title, "content_message_ids": [mid], "sessions": parse_sessions(text, urls), "platforms": domains(urls), "boundary_confidence": "explicit preceding header"}
            pending = None
        else:
            raw_title = explicit_title or f"Ambiguous content message {mid}"
            course = {"message_id": None, "raw_title": raw_title, "subject": None, "teacher": None, "program": None, "content_message_ids": [mid], "sessions": parse_sessions(text, urls), "platforms": domains(urls), "boundary_confidence": "ambiguous standalone content"}
            ambiguities.append({"message_id": mid, "reason": "URL content without an explicit adjacent course header"})
        courses.append(course)
        for sidx, session in enumerate(course["sessions"]):
            for url in session["urls"]:
                duplicate_locations[url].append({"course_index": len(courses)-1, "message_id": mid, "session_index": sidx, "heading": session["heading"]})

    duplicates = {url: locs for url, locs in duplicate_locations.items() if len(locs) > 1}
    return {
        "courses": courses,
        "stats": {
            "courses_detected": len(courses),
            "sessions_detected": sum(len(c["sessions"]) for c in courses),
            "urls_detected": sum(len(s["urls"]) for c in courses for s in c["sessions"]),
            "duplicate_urls": sum(len(v) - 1 for v in duplicates.values()),
            "duplicate_url_values": len(duplicates),
            "ambiguous_course_boundaries": len(ambiguities),
        },
        "duplicate_urls": duplicates,
        "ambiguous_course_boundaries": ambiguities,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default="result.json")
    parser.add_argument("-o", "--output", default="extracted.json")
    args = parser.parse_args()
    extracted = extract(Path(args.input))
    Path(args.output).write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(extracted["stats"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
