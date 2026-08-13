#!/usr/bin/env python3
"""Extract Telegram course groups using explicit course-header boundaries.

A course begins at messages that match this structure:

    💎 کلاس‌های [SUBJECT] 💎
    ✔️ [TEACHER] (or ☑️ [TEACHER])
    ⬅️ [COURSE NAME / PROGRAM]

Every later non-header message is attached to the current course until the next
course header. Messages before the first header are emitted as unassigned.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

HEADER_RE = re.compile(
    r"💎\s*(?:ادامه\s+)?کلاس[‌ ]های\s+(?P<subject>.+?)\s*💎"
    r".*?(?:✔️|☑️)\s*(?P<teacher>.+?)\s*(?:\n|$)"
    r".*?⬅️\s*(?P<course_name>.+?)\s*(?:\n|$)",
    re.S,
)
URL_RE = re.compile(r"https?://[^\s)\]}،,؛]+")
SESSION_RE = re.compile(r"(?:جلسه|جلسه‌ی|جلسهٔ|جلسه\s*ی)\s*(?P<number>[۰-۹0-9]+)?\s*[:：\-.،]?\s*(?P<title>[^\n]*)")
YEAR_RE = re.compile(r"(?<!\d)(?P<year>[۰-۹0-9]{3,4})(?!\d)")


def message_text(value: Any) -> str:
    """Return Telegram export text as plain text while preserving emoji text."""
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            parts.append(str(item.get("text", "")))
    return "".join(parts)


def normalize(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value.strip())


def parse_header(text: str) -> dict[str, Any] | None:
    match = HEADER_RE.search(text)
    if not match:
        return None
    course_name = normalize(match.group("course_name"))
    year_match = YEAR_RE.search(course_name)
    return {
        "subject": normalize(match.group("subject")),
        "teacher": normalize(match.group("teacher")),
        "course_name": course_name,
        "program_year": year_match.group("year") if year_match else None,
    }


def urls_from_message(message: dict[str, Any], text: str) -> list[dict[str, str | None]]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_RE.finditer(text):
        urls.append(match.group(0))
    for entity in message.get("text_entities", []):
        href = entity.get("href") if isinstance(entity, dict) else None
        if href and href.startswith(("http://", "https://")):
            urls.append(href)
    output: list[dict[str, str | None]] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        output.append({"url": url, "provider": urlparse(url).netloc.lower() or None})
    return output


def sessions_from_text(text: str) -> list[dict[str, str | None]]:
    sessions: list[dict[str, str | None]] = []
    for match in SESSION_RE.finditer(text):
        title = normalize(match.group("title")) or None
        sessions.append({
            "heading": normalize(match.group(0)),
            "session_number": match.group("number"),
            "title": title,
        })
    return sessions


@dataclass
class Course:
    header_message_id: int
    subject: str
    teacher: str
    course_name: str
    program_year: str | None
    content_message_ids: list[int] = field(default_factory=list)
    sessions: list[dict[str, Any]] = field(default_factory=list)
    video_urls: list[dict[str, str | int | None]] = field(default_factory=list)

    def attach(self, message: dict[str, Any], text: str) -> None:
        message_id = message.get("id")
        self.content_message_ids.append(message_id)
        for session in sessions_from_text(text):
            self.sessions.append({"message_id": message_id, **session})
        for video in urls_from_message(message, text):
            self.video_urls.append({"message_id": message_id, **video})


def extract(data: dict[str, Any]) -> dict[str, Any]:
    courses: list[Course] = []
    unassigned = {"message_ids": [], "sessions": [], "video_urls": []}
    current: Course | None = None

    for message in sorted(data.get("messages", []), key=lambda item: item.get("id", 0)):
        text = message_text(message.get("text", ""))
        header = parse_header(text)
        if header:
            current = Course(header_message_id=message["id"], **header)
            courses.append(current)
            continue
        if current is None:
            unassigned["message_ids"].append(message.get("id"))
            for session in sessions_from_text(text):
                unassigned["sessions"].append({"message_id": message.get("id"), **session})
            for video in urls_from_message(message, text):
                unassigned["video_urls"].append({"message_id": message.get("id"), **video})
        else:
            current.attach(message, text)

    provider_counts: dict[str, int] = defaultdict(int)
    for course in courses:
        for video in course.video_urls:
            if video["provider"]:
                provider_counts[str(video["provider"])] += 1

    return {
        "source": {"name": data.get("name"), "id": data.get("id"), "message_count": len(data.get("messages", []))},
        "course_count": len(courses),
        "unassigned": unassigned,
        "provider_counts": dict(sorted(provider_counts.items())),
        "courses": [course.__dict__ for course in courses],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract StreamClass courses from Telegram result.json")
    parser.add_argument("input", nargs="?", default="result.json")
    parser.add_argument("-o", "--output", default="courses.json")
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as fh:
        data = json.load(fh)
    extracted = extract(data)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(extracted, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
