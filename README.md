# mc-milestones

A curated, auto-updated dataset of all Minecraft milestones (Java advancements and Bedrock achievements) — compiled from official sources with multi-language support.

## Data Sources

| Edition | Source | License |
|---------|--------|---------|
| **Java Advancements** | [misode/mcmeta](https://github.com/misode/mcmeta) (data-json + assets-json) | Generated data (Mojang content) |
| **Bedrock Achievements** | [Minecraft Wiki](https://minecraft.wiki/w/Achievement) | CC BY-NC-SA 3.0 |
| **Bedrock Translations** | [Mojang/bedrock-samples](https://github.com/Mojang/bedrock-samples) resource_pack/texts/*.lang | Mojang sample code |

## Files

```
milestones.json              # Combined index (Java + Bedrock, deduplicated)
data/
├── java/advancements.json   # Java advancements with 132 locales
└── bedrock/achievements.json # Bedrock achievements with 29 locales
```

### Current Snapshot

- **Java**: 126 advancements (version 26.1.2) — 132 locales
- **Bedrock**: 135 achievements — 31 with 29-locale official translations, 104 English-only
- **Combined**: 223 milestones (42 matched, 86 Java-only, 95 Bedrock-only)

## Usage as an API

Use `raw.githubusercontent.com` URLs to fetch the latest data directly:

```sh
# Combined milestones (all editions)
curl -s https://raw.githubusercontent.com/danielytuk/mc-milestones/main/milestones.json

# Java advancements (full with translations)
curl -s https://raw.githubusercontent.com/danielytuk/mc-milestones/main/data/java/advancements.json

# Bedrock achievements
curl -s https://raw.githubusercontent.com/danielytuk/mc-milestones/main/data/bedrock/achievements.json
```

### Query Examples

Get the English title for a Java advancement by its ID:

```python
import json, urllib.request

url = "https://raw.githubusercontent.com/danielytuk/mc-milestones/main/data/java/advancements.json"
data = json.loads(urllib.request.urlopen(url).read())

adv = data["advancements"]["minecraft:adventure/adventuring_time"]
print(adv["display"]["title"]["localized"]["en_US"])
# "Adventuring Time"
```

Find which milestones exist in both editions:

```python
import json, urllib.request

url = "https://raw.githubusercontent.com/danielytuk/mc-milestones/main/milestones.json"
data = json.loads(urllib.request.urlopen(url).read())

shared = [m for m in data["milestones"] if len(m["editions"]) == 2]
print(f"{len(shared)} milestones shared between Java and Bedrock")
```

Get all localized names for a Bedrock achievement:

```python
import json, urllib.request

url = "https://raw.githubusercontent.com/danielytuk/mc-milestones/main/data/bedrock/achievements.json"
data = json.loads(urllib.request.urlopen(url).read())

for a in data["achievements"]:
    if a["id"] == "taking_inventory":
        print(a["title"]["localized"])
        # {'bg_BG': 'Проверка на наличностите', 'cs_CZ': 'Inventarizace', ...}
```

## Updates

Data is refreshed weekly via GitHub Actions (Sunday 6am UTC) and can be manually triggered from the Actions tab. The pipeline detects new Minecraft versions automatically through mcmeta's version manifest.

## Data Format

### `milestones.json`

```json
{
  "generated": "2026-06-10",
  "java_version": "26.1.2",
  "java_advancement_count": 126,
  "bedrock_achievement_count": 135,
  "total_milestones": 223,
  "milestones": [
    {
      "id": "adventuring_time",
      "milestone": "Adventuring Time",
      "editions": ["java", "bedrock"],
      "java": { "id": "minecraft:adventure/adventuring_time", "category": "adventure" },
      "bedrock": { "id": "adventuring_time", "category": "exploring_your_world", "gamerscore": 40, "trophy_type": "Silver" }
    },
    { "id": "arbalistic", "milestone": "Arbalistic", "editions": ["java"], "java": {...}, "bedrock": null },
    { "id": "awarded_all_trophies", "milestone": "Awarded all trophies", "editions": ["bedrock"], "java": null, "bedrock": {...} }
  ]
}
```

## License

- **Code** (scripts, workflows): MIT — see [LICENSE](LICENSE)
- **Bedrock achievement data** sourced from the Minecraft Wiki: CC BY-NC-SA 3.0 — see [DATA_LICENSE.md](DATA_LICENSE.md)
- **Java advancement data** and **Bedrock translations** are Mojang game content; all rights belong to Mojang Studios
