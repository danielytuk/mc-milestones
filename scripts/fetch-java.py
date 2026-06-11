#!/usr/bin/env python3
"""Fetch Java Edition advancements from misode/mcmeta with multi-locale translations."""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import zipfile
import io
from pathlib import Path

MCMETA_OWNER = "misode"
MCMETA_REPO = "mcmeta"
RAW_BASE = f"https://raw.githubusercontent.com/{MCMETA_OWNER}/{MCMETA_REPO}"
API_BASE = f"https://api.github.com/repos/{MCMETA_OWNER}/{MCMETA_REPO}"
OUTPUT_DIR = Path("data/java")
OUTPUT_FILE = OUTPUT_DIR / "advancements.json"

SKIP_LOCALES = {"deprecated", "lol_us", "oj_ca", "tlh_aa", "jbo_en", "qya_aa", "zlm_arab"}


def fetch_url(url):
    headers = {"User-Agent": "mc-milestones/1.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def fetch_json(url):
    return json.loads(fetch_url(url).decode("utf-8"))


def snake_to_pascal(locale):
    parts = locale.split("_")
    if len(parts) == 1:
        return locale
    return parts[0].lower() + "_" + "_".join(p.upper() for p in parts[1:])


def find_latest_stable():
    url = f"{RAW_BASE}/summary/versions/data.json"
    versions = fetch_json(url)
    for v in versions:
        if v.get("stable"):
            return v
    print("ERROR: No stable version found", file=sys.stderr)
    sys.exit(1)


def get_github_contents(path, ref):
    import urllib.parse
    encoded = urllib.parse.quote(path)
    url = f"{API_BASE}/contents/{encoded}?ref={urllib.parse.quote(ref)}"
    return fetch_json(url)


def discover_advancement_files(tag):
    files = []
    try:
        categories = get_github_contents("data/minecraft/advancement", tag)
    except Exception as e:
        print(f"ERROR: Failed to list advancements: {e}", file=sys.stderr)
        sys.exit(1)

    for cat_entry in categories:
        if cat_entry["type"] != "dir":
            continue
        category = cat_entry["name"]
        try:
            cat_files = get_github_contents(f"data/minecraft/advancement/{category}", tag)
        except Exception:
            continue
        for file_entry in cat_files:
            if file_entry["type"] == "file" and file_entry["name"].endswith(".json"):
                path = f"data/minecraft/advancement/{category}/{file_entry['name']}"
                files.append({
                    "category": category,
                    "path": path,
                    "advancement_id": f"minecraft:{category}/{file_entry['name'].replace('.json', '')}",
                })
    return files


def download_locale_archive(tag):
    url = f"https://github.com/{MCMETA_OWNER}/{MCMETA_REPO}/archive/refs/tags/{tag}.zip"
    print(f"  Downloading {tag}.zip (all locales in one request)...")
    data = fetch_url(url)
    print(f"    Received {len(data)} bytes")
    return data


def extract_locales_from_zip(zip_data):
    lang_data = {}
    locales = []
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        names = z.namelist()
        lang_prefix = None
        for name in names:
            if name.endswith(".json") and "/lang/" in name:
                lang_prefix = name[:name.index("/assets")]
                break
        if not lang_prefix:
            raise Exception("No language files found in archive")
        lang_dir = f"{lang_prefix}/assets/minecraft/lang/"
        for name in names:
            if not name.startswith(lang_dir) or not name.endswith(".json"):
                continue
            locale = name[len(lang_dir):-5]
            if locale in SKIP_LOCALES:
                continue
            with z.open(name) as f:
                data = json.loads(f.read().decode("utf-8"))
                lang_data[locale] = data
                locales.append(locale)
    return sorted(locales), lang_data


def process_display(display, lang_data):
    result = {}
    for field in ("title", "description"):
        if field not in display:
            continue
        comp = display[field]
        if isinstance(comp, dict) and "translate" in comp:
            key = comp["translate"]
            localized = {}
            for locale, translations in lang_data.items():
                pascal = snake_to_pascal(locale)
                value = translations.get(key)
                if value is not None:
                    localized[pascal] = value
            result[field] = {"translate": key, "localized": localized}
        else:
            result[field] = comp
    if "icon" in display:
        icon = display["icon"]
        result["icon"] = {"item": icon["item"]} if isinstance(icon, dict) and "item" in icon else icon
    for field in ("frame", "background", "show_toast", "announce_to_chat", "hidden"):
        if field in display:
            result[field] = display[field]
    return result


def main():
    print("=== Fetching Java Advancements ===")

    print("Finding latest stable version...")
    version_info = find_latest_stable()
    version_id = version_info["id"]
    data_version = version_info.get("data_version")
    print(f"  Version: {version_id} (data v{data_version})")

    data_tag = f"{version_id}-data-json"
    assets_tag = f"{version_id}-assets-json"

    print("Downloading locale archive...")
    zip_data = download_locale_archive(assets_tag)
    print("Extracting locale data...")
    locales, lang_data = extract_locales_from_zip(zip_data)
    print(f"  Loaded {len(locales)} locales")

    print("Discovering advancement files...")
    advancement_files = discover_advancement_files(data_tag)
    print(f"  Found {len(advancement_files)} advancements")

    print("Fetching and processing advancements...")
    advancements = {}
    total = len(advancement_files)
    for i, info in enumerate(advancement_files):
        try:
            url = f"{RAW_BASE}/{data_tag}/{info['path']}"
            data = fetch_json(url)
            if data:
                entry = {"category": info["category"]}
                if "parent" in data:
                    entry["parent"] = data["parent"]
                if "display" in data:
                    entry["display"] = process_display(data["display"], lang_data)
                advancements[info["advancement_id"]] = entry
        except Exception as e:
            print(f"    Warning: {info['advancement_id']}: {e}", file=sys.stderr)
        if (i + 1) % 20 == 0 or i + 1 == total:
            print(f"    ... {i+1}/{total}", flush=True)

    output_locales = sorted(set(snake_to_pascal(loc) for loc in locales))

    output = {
        "version": version_id,
        "data_version": data_version,
        "fetched": time.strftime("%Y-%m-%d"),
        "locales": output_locales,
        "advancement_count": len(advancements),
        "advancements": advancements,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Written {len(advancements)} advancements to {OUTPUT_FILE}")
    print(f"  Locales: {len(output_locales)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
