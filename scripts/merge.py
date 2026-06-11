#!/usr/bin/env python3
"""Merge Java advancements + Bedrock achievements into milestones.json."""

import json
import os
import re
import sys
import time
from pathlib import Path

JAVA_FILE = Path("data/java/advancements.json")
BEDROCK_FILE = Path("data/bedrock/achievements.json")
OVERRIDES_FILE = Path("scripts/overrides.json")
OUTPUT_FILE = Path("milestones.json")


def get_english_title(adv_entry):
    """Extract the English title from an advancement/achievement entry."""
    display = adv_entry.get("display") or {}
    title = display.get("title") or {}

    localized = title.get("localized", {}) if isinstance(title, dict) else {}
    for locale in ("en_US", "en_us", "en_GB", "en_gb"):
        if locale in localized:
            return localized[locale]

    text = title.get("text", "") if isinstance(title, dict) else ""
    if text:
        return text

    translate = title.get("translate", "") if isinstance(title, dict) else ""
    if translate:
        return translate

    return ""


def get_english_desc(adv_entry):
    display = adv_entry.get("display") or {}
    desc = display.get("description") or {}
    localized = desc.get("localized", {}) if isinstance(desc, dict) else {}
    for locale in ("en_US", "en_us", "en_GB", "en_gb"):
        if locale in localized:
            return localized[locale]
    text = desc.get("text", "") if isinstance(desc, dict) else ""
    if text:
        return text
    return ""


def get_bedrock_title(entry):
    title = entry.get("title", {})
    if isinstance(title, str):
        return title
    localized = title.get("localized", {}) if isinstance(title, dict) else {}
    for locale in ("en_US", "en_GB"):
        if locale in localized:
            return localized[locale]
    return ""


def normalize(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def auto_match(java_advs, bedrock_achs):
    """Auto-match Java and Bedrock entries by normalized title."""
    java_by_norm = {}
    for jid, jdata in java_advs.items():
        title = get_english_title(jdata)
        if title:
            java_by_norm.setdefault(normalize(title), []).append(jid)

    bedrock_by_norm = {}
    for i, bdata in enumerate(bedrock_achs):
        title = get_bedrock_title(bdata)
        if title:
            bedrock_by_norm.setdefault(normalize(title), []).append(i)

    matches = []
    for norm, jids in java_by_norm.items():
        if norm in bedrock_by_norm:
            for jid in jids:
                for bidx in bedrock_by_norm[norm]:
                    matches.append((jid, bidx))

    return matches


def load_overrides(path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"java_to_bedrock": {}, "bedrock_to_java": {}}


def main():
    print("=== Merging Milestones ===")

    if not JAVA_FILE.exists():
        print(f"ERROR: {JAVA_FILE} not found. Run fetch-java.py first.", file=sys.stderr)
        sys.exit(1)
    if not BEDROCK_FILE.exists():
        print(f"ERROR: {BEDROCK_FILE} not found. Run fetch-bedrock.py first.", file=sys.stderr)
        sys.exit(1)

    print("Loading Java advancements...")
    with open(JAVA_FILE, "r", encoding="utf-8") as f:
        java_data = json.load(f)
    java_advs = java_data.get("advancements", {})
    java_version = java_data.get("version", "unknown")
    print(f"  {len(java_advs)} advancements (version {java_version})")

    print("Loading Bedrock achievements...")
    with open(BEDROCK_FILE, "r", encoding="utf-8") as f:
        bedrock_data = json.load(f)
    bedrock_achs = bedrock_data.get("achievements", [])
    print(f"  {len(bedrock_achs)} achievements")

    print("Loading overrides...")
    overrides = load_overrides(OVERRIDES_FILE)
    java_to_bedrock_override = overrides.get("java_to_bedrock", {})
    bedrock_to_java_override = overrides.get("bedrock_to_java", {})
    print(f"  {len(java_to_bedrock_override)} java->bedrock, {len(bedrock_to_java_override)} bedrock->java")

    print("Auto-matching...")
    auto_matches = auto_match(java_advs, bedrock_achs)
    matched_jids = set()
    matched_bidxs = set()

    milestones = []

    for jid, bidx in auto_matches:
        java_entry = java_advs[jid]
        bedrock_entry = bedrock_achs[bidx]
        matched_jids.add(jid)
        matched_bidxs.add(bidx)

        jtitle = get_english_title(java_entry)
        btitle = get_bedrock_title(bedrock_entry)

        common_title = jtitle or btitle
        milestones.append({
            "id": slugify(common_title) if common_title else f"{jid}-{bidx}",
            "milestone": common_title or jid,
            "editions": ["java", "bedrock"],
            "java": {
                "id": jid,
                "category": java_entry.get("category"),
            },
            "bedrock": {
                "id": bedrock_entry.get("id"),
                "category": bedrock_entry.get("category"),
                "gamerscore": bedrock_entry.get("gamerscore"),
                "trophy_type": bedrock_entry.get("trophy_type"),
            },
        })

    java_only = []
    for jid in sorted(java_advs.keys()):
        if jid not in matched_jids:
            entry = java_advs[jid]
            title = get_english_title(entry) or jid
            milestones.append({
                "id": slugify(title),
                "milestone": title,
                "editions": ["java"],
                "java": {
                    "id": jid,
                    "category": entry.get("category"),
                },
                "bedrock": None,
            })
            java_only.append(jid)

    bedrock_only = []
    for idx, entry in enumerate(bedrock_achs):
        if idx not in matched_bidxs:
            title = get_bedrock_title(entry)
            milestones.append({
                "id": entry.get("id"),
                "milestone": title or entry.get("id"),
                "editions": ["bedrock"],
                "java": None,
                "bedrock": {
                    "id": entry.get("id"),
                    "category": entry.get("category"),
                    "gamerscore": entry.get("gamerscore"),
                    "trophy_type": entry.get("trophy_type"),
                },
            })
            bedrock_only.append(entry.get("id"))

    output = {
        "generated": time.strftime("%Y-%m-%d"),
        "java_version": java_version,
        "java_advancement_count": len(java_advs),
        "bedrock_achievement_count": len(bedrock_achs),
        "total_milestones": len(milestones),
        "matched_count": len(auto_matches),
        "java_only_count": len(java_only),
        "bedrock_only_count": len(bedrock_only),
        "milestones": milestones,
        "_stats": {
            "java_only": java_only,
            "bedrock_only": bedrock_only,
        },
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Written {len(milestones)} milestones to {OUTPUT_FILE}")
    print(f"  Matched: {len(auto_matches)}")
    print(f"  Java-only: {len(java_only)}")
    print(f"  Bedrock-only: {len(bedrock_only)}")
    return 0


def slugify(title):
    s = title.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s)
    s = s.strip("_")
    return s or "unknown"


if __name__ == "__main__":
    sys.exit(main())
