#!/usr/bin/env python3
"""Fetch Bedrock Edition achievements from Minecraft Wiki + Mojang/bedrock-samples."""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

WIKI_URL = "https://minecraft.wiki/w/Achievement?action=raw"
BEDROCK_SAMPLES_OWNER = "Mojang"
BEDROCK_SAMPLES_REPO = "bedrock-samples"
BEDROCK_SAMPLES_BRANCH = "main"
BEDROCK_LANG_PATH = "resource_pack/texts"
RAW_BEDROCK = f"https://raw.githubusercontent.com/{BEDROCK_SAMPLES_OWNER}/{BEDROCK_SAMPLES_REPO}/{BEDROCK_SAMPLES_BRANCH}"
API_BEDROCK = f"https://api.github.com/repos/{BEDROCK_SAMPLES_OWNER}/{BEDROCK_SAMPLES_REPO}"

OUTPUT_DIR = Path("data/bedrock")
OUTPUT_FILE = OUTPUT_DIR / "achievements.json"


def fetch_url(url, max_retries=3):
    headers = {"User-Agent": "mc-milestones/1.0"}
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(1 * (attempt + 1))
    return None


def fetch_json(url):
    text = fetch_url(url)
    return json.loads(text) if text else None


def slugify(title):
    """Convert achievement title to a snake_case ID."""
    s = title.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s)
    s = s.strip("_")
    return s or "unknown"


def strip_wiki_markup(text):
    """Remove wiki formatting from text."""
    if not text:
        return text
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'''?([^']*)'''?", r"\1", text)
    while "{{" in text:
        depth = 0
        start = text.find("{{")
        j = start
        while j < len(text) - 1:
            if text[j:j+2] == "{{":
                depth += 1
                j += 2
            elif text[j:j+2] == "}}":
                depth -= 1
                j += 2
                if depth == 0:
                    text = text[:start] + text[j:]
                    break
            else:
                j += 1
    text = re.sub(r"<br\s*/?>", ", ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_achievement_rows(text):
    """Parse the wiki raw text and extract achievement data."""
    lines = text.split("\n")

    category_matches = []
    for i, line in enumerate(lines):
        m = re.match(r"^===\s*(.+?)\s*===$", line)
        if m:
            category_matches.append((i, m.group(1).strip()))

    achievements = []

    for cat_idx, (cat_line, category) in enumerate(category_matches):
        next_cat_line = (
            category_matches[cat_idx + 1][0]
            if cat_idx + 1 < len(category_matches)
            else len(lines)
        )

        block_text = "\n".join(lines[cat_line:next_cat_line])

        in_table = False
        row_buf = []
        for line in block_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("{{AchievementTable"):
                in_table = True
                continue
            if stripped.startswith("{{AchievementTable|foot}}"):
                in_table = False
                continue
            if in_table:
                row_buf.append(stripped)

        rows_text = "\n".join(row_buf)

        i = 0
        while i < len(rows_text):
            idx = rows_text.find("{{AchievementRow", i)
            if idx == -1:
                break
            depth = 0
            j = idx
            while j < len(rows_text) - 1:
                if rows_text[j:j+2] == "{{":
                    depth += 1
                    j += 2
                elif rows_text[j:j+2] == "}}":
                    depth -= 1
                    j += 2
                    if depth == 0:
                        end = j
                        break
                else:
                    j += 1
            block = rows_text[idx:end]
            i = end

            row = parse_single_row(block)
            if row:
                row["category"] = slugify(category)
                row["category_display"] = category.strip()
                achievements.append(row)

    return achievements


def parse_single_row(block):
    """Parse a {{AchievementRow ... }} template block with nested template support."""
    inner = block[len("{{AchievementRow"):-2].strip()

    brace_depth = 0
    link_depth = 0
    parts = []
    buf = []
    i = 0
    while i < len(inner):
        if inner[i:i+2] == "{{":
            brace_depth += 1
            buf.append("{{")
            i += 2
        elif inner[i:i+2] == "}}":
            brace_depth -= 1
            buf.append("}}")
            i += 2
        elif inner[i:i+2] == "[[":
            link_depth += 1
            buf.append("[[")
            i += 2
        elif inner[i:i+2] == "]]":
            link_depth -= 1
            buf.append("]]")
            i += 2
        elif brace_depth == 0 and link_depth == 0 and inner[i] == "|":
            parts.append("".join(buf).strip())
            buf = []
            i += 1
        else:
            buf.append(inner[i])
            i += 1
    if buf:
        parts.append("".join(buf).strip())

    # First part is always empty (whitespace before first |), discard it
    if parts and not parts[0].strip():
        parts = parts[1:]

    params = {"_unnamed": []}
    for part in parts:
        # Strip {{...}} template bodies before checking for =
        # This prevents template-internal = chars from polluting AchievementRow params
        cleaned = strip_wiki_markup(part)
        if cleaned and "=" in cleaned:
            key, value = cleaned.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if key == "title":
                params[key] = value
        else:
            # Keep original part (with templates) for later strip_wiki_markup calls
            params["_unnamed"].append(part)

    if "title" not in params:
        return None

    title = strip_wiki_markup(params["title"])
    unnamed = params["_unnamed"]
    description = strip_wiki_markup(unnamed[0]) if len(unnamed) > 0 else ""
    actual_req = strip_wiki_markup(unnamed[1]) if len(unnamed) > 1 else None
    gamerscore_str = unnamed[2].strip() if len(unnamed) > 2 else "0"
    trophy_type = unnamed[3].strip() if len(unnamed) > 3 else ""
    rewards_raw = unnamed[4].strip() if len(unnamed) > 4 else ""

    try:
        gamerscore = int(gamerscore_str) if gamerscore_str else 0
    except (ValueError, TypeError):
        gamerscore = 0

    if actual_req in (None, "", "—"):
        actual_req = None
    if trophy_type in ("", "—"):
        trophy_type = None
    if rewards_raw in ("", "—"):
        rewards_raw = None

    return {
        "id": slugify(title),
        "title": title,
        "description": description,
        "actual_requirements": actual_req if actual_req else None,
        "gamerscore": gamerscore,
        "trophy_type": trophy_type,
        "rewards": rewards_raw if rewards_raw else None,
    }


def discover_lang_files():
    """Discover all .lang files available in bedrock-samples texts/."""
    url = f"{API_BEDROCK}/contents/{BEDROCK_LANG_PATH}?ref={BEDROCK_SAMPLES_BRANCH}"
    data = fetch_json(url)
    if not data:
        print("WARNING: Could not list bedrock-samples lang files", file=sys.stderr)
        return []
    return [
        entry["name"].replace(".lang", "")
        for entry in data
        if entry["type"] == "file" and entry["name"].endswith(".lang")
    ]


def parse_lang(text):
    """Parse a .lang file into a key-value dict."""
    result = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def build_translation_lookup(locales):
    """Fetch all .lang files and build a lookup by English title."""
    translations_by_key = {}
    locale_set = {}

    en_data = None
    for locale in locales:
        url = f"{RAW_BEDROCK}/{BEDROCK_LANG_PATH}/{locale}.lang"
        try:
            text = fetch_url(url)
            if text:
                parsed = parse_lang(text)
                locale_set[locale] = parsed
                if locale == "en_US":
                    en_data = parsed
        except Exception as e:
            print(f"  Warning: Could not fetch {locale}.lang: {e}", file=sys.stderr)

    if not en_data:
        print("ERROR: Could not fetch en_US.lang from bedrock-samples", file=sys.stderr)
        return {}, {}

    for key, en_title in en_data.items():
        if key.startswith("achievement.") and not key.endswith(".desc"):
            translations = {}
            for locale, data in locale_set.items():
                locale_key = locale.replace("_", "_")
                val = data.get(key)
                if val:
                    translations[locale] = val
            translations_by_key[key] = translations

    title_to_key = {}
    for key, en_title in en_data.items():
        if key.startswith("achievement.") and not key.endswith(".desc"):
            title_to_key[en_title] = key

    desc_translations = {}
    for key, en_desc in en_data.items():
        if key.startswith("achievement.") and key.endswith(".desc"):
            descs = {}
            for locale, data in locale_set.items():
                val = data.get(key)
                if val:
                    descs[locale] = val
            desc_translations[key] = descs

    return title_to_key, locale_set


def match_translations(achievements, title_to_key, locale_data):
    """Match wiki achievements to bedrock-samples translations."""
    all_locales = sorted(locale_data.keys())
    matched_count = 0

    for achievement in achievements:
        title = achievement["title"]
        key = title_to_key.get(title)

        if key:
            title_translations = {}
            desc_translations = {}

            for locale, data in locale_data.items():
                t_val = data.get(key)
                if t_val:
                    title_translations[locale] = t_val
                d_val = data.get(f"{key}.desc")
                if d_val:
                    desc_translations[locale] = d_val

            achievement["title"] = {
                "translate": key,
                "localized": title_translations,
            }
            if desc_translations:
                achievement["description"] = {
                    "translate": f"{key}.desc",
                    "localized": desc_translations,
                }
            matched_count += 1
        else:
            achievement["title"] = {"localized": {"en_US": title}}
            achievement["description"] = {"localized": {"en_US": achievement["description"]}}

    return matched_count


def main():
    print("=== Fetching Bedrock Achievements ===")

    print("Fetching wiki page...")
    try:
        wiki_text = fetch_url(WIKI_URL)
        if not wiki_text:
            print("ERROR: Could not fetch wiki page", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to fetch wiki: {e}", file=sys.stderr)
        sys.exit(1)

    print("Parsing achievement rows...")
    achievements = parse_achievement_rows(wiki_text)
    if not achievements:
        print("ERROR: No achievements parsed from wiki", file=sys.stderr)
        sys.exit(1)
    print(f"  Found {len(achievements)} achievements")

    print("Discovering bedrock-samples lang files...")
    locales = discover_lang_files()
    print(f"  Found {len(locales)} locales")

    print("Fetching and parsing lang files...")
    title_to_key, locale_data = build_translation_lookup(locales)
    if not locale_data:
        print("ERROR: No locale data loaded", file=sys.stderr)
        sys.exit(1)

    print("Matching translations...")
    matched = match_translations(achievements, title_to_key, locale_data)
    print(f"  Matched {matched}/{len(achievements)} to official translations")

    all_locales = sorted(locale_data.keys())

    output = {
        "source": "https://minecraft.wiki/w/Achievement",
        "source_license": "CC BY-NC-SA 3.0",
        "translation_source": "https://github.com/Mojang/bedrock-samples",
        "fetched": time.strftime("%Y-%m-%d"),
        "locales": all_locales,
        "total": len(achievements),
        "translated_count": matched,
        "untranslated_count": len(achievements) - matched,
        "achievements": achievements,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Written {len(achievements)} achievements to {OUTPUT_FILE}")
    print(f"  Translated: {matched}, English-only: {len(achievements) - matched}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
