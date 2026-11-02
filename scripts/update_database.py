#!/usr/bin/env python3
"""Update the embedded route database in index.html from a Yandex CSV export."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


REQUIRED_COLUMNS = {"id", "name", "description", "lat", "lon", "category"}
APP_CATEGORIES = {
    "еда",
    "кофе",
    "бар",
    "музыка",
    "шопинг",
    "театр",
    "кино",
    "галереи",
    "книги",
    "природа",
    "бильярд",
    "отдых",
    "спорт",
    "особое",
}

# Defaults for Yandex collection categories. Existing places keep the more
# specific category already curated in the app.
CATEGORY_MAP = {
    "еда": "еда",
    "бар": "бар",
    "одежда": "шопинг",
    "театр": "театр",
    "особое место": "особое",
    "спа и массаж": "отдых",
    "спорт": "спорт",
    "развлечения": "особое",
    "книги и библиотеки": "книги",
    "музеи и культурные пространства": "галереи",
    "интерьер и подарки": "шопинг",
    "клуб": "музыка",
    "кино": "кино",
    "красота": "отдых",
    "шопинг": "шопинг",
    "отель": "отдых",
    "бассейн": "спорт",
    "вода и пляжи": "спорт",
    "виды и прогулки": "природа",
    "парки и природа": "природа",
    "здоровье": "отдых",
}

# Ambiguous new records in the 2026-11-01 export.
CATEGORY_OVERRIDES = {
    "MORE эмоций": "шопинг",
    "ДК Рассвет": "музыка",
    "Музей Транспорта": "галереи",
}

SCRIPT_RE = re.compile(
    r'(<script type="application/json" id="(?P<id>j-db|j-mc)">)'
    r'(?P<data>.*?)'
    r'(</script>)',
    re.DOTALL,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Yandex CSV export")
    parser.add_argument("--html", type=Path, default=Path("index.html"))
    parser.add_argument("--bot", type=Path, default=Path("bot.py"))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def embedded_json(html: str, script_id: str):
    for match in SCRIPT_RE.finditer(html):
        if match.group("id") == script_id:
            return json.loads(match.group("data"))
    raise ValueError(f"Embedded JSON block {script_id!r} was not found")


def replace_embedded_json(html: str, script_id: str, value) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def replace(match: re.Match[str]) -> str:
        if match.group("id") != script_id:
            return match.group(0)
        return f"{match.group(1)}{payload}{match.group(4)}"

    updated, count = SCRIPT_RE.subn(replace, html)
    if count < 1 or embedded_json(updated, script_id) != value:
        raise ValueError(f"Failed to replace embedded JSON block {script_id!r}")
    return updated


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing_columns = REQUIRED_COLUMNS - columns
        if missing_columns:
            raise ValueError(f"CSV is missing columns: {sorted(missing_columns)}")
        rows = list(reader)

    duplicate_ids = [key for key, count in Counter(row["id"] for row in rows).items() if count > 1]
    if duplicate_ids:
        raise ValueError(f"CSV contains duplicate ids: {duplicate_ids[:10]}")

    for row_number, row in enumerate(rows, start=2):
        missing_values = [key for key in REQUIRED_COLUMNS if not (row.get(key) or "").strip()]
        if missing_values:
            raise ValueError(f"CSV row {row_number} has empty fields: {missing_values}")
        lat, lon = float(row["lat"]), float(row["lon"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"CSV row {row_number} has invalid coordinates: {lat}, {lon}")
    return rows


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_metro(lat: float, lon: float, metro_coords: dict[str, list[float]]) -> list[str]:
    distances = sorted(
        (haversine(lat, lon, coords[0], coords[1]), name)
        for name, coords in metro_coords.items()
    )
    nearby = [name for distance, name in distances if distance <= 900]
    if nearby:
        return nearby[:4]
    # The existing database assigns one practical reference station to remote
    # Moscow places, but leaves true out-of-town destinations without a metro.
    if distances and distances[0][0] <= 5_000:
        return [distances[0][1]]
    return []


def make_indexes(current: list[dict]):
    by_id = {str(item["id"]): item for item in current if "id" in item}
    by_exact = {
        (item["n"], round(float(item["la"]), 6), round(float(item["lo"]), 6)): item
        for item in current
    }
    by_name: dict[str, list[dict]] = defaultdict(list)
    for item in current:
        by_name[item["n"]].append(item)
    return by_id, by_exact, by_name


def update_database(rows: list[dict[str, str]], current: list[dict], metro_coords: dict[str, list[float]]):
    by_id, by_exact, by_name = make_indexes(current)
    stats = Counter()
    updated = []

    for row in rows:
        lat, lon = float(row["lat"]), float(row["lon"])
        exact_key = (row["name"], round(lat, 6), round(lon, 6))
        previous = by_id.get(row["id"]) or by_exact.get(exact_key)
        moved = False
        if previous is None and len(by_name[row["name"]]) == 1:
            previous = by_name[row["name"]][0]
            moved = True

        if previous is not None:
            category = previous["c"]
            metro = nearest_metro(lat, lon, metro_coords) if moved else list(previous.get("metro", []))
            stats["matched"] += 1
            if moved:
                stats["moved"] += 1
        else:
            category = CATEGORY_OVERRIDES.get(row["name"], CATEGORY_MAP.get(row["category"]))
            if category is None:
                raise ValueError(
                    f"No app category mapping for {row['category']!r} ({row['name']!r})"
                )
            metro = nearest_metro(lat, lon, metro_coords)
            stats["new"] += 1

        if category not in APP_CATEGORIES:
            raise ValueError(f"Unsupported app category {category!r} for {row['name']!r}")

        updated.append(
            {
                "id": row["id"],
                "n": row["name"].strip(),
                "d": row["description"].strip(),
                "la": lat,
                "lo": lon,
                "c": category,
                "metro": metro,
            }
        )

    return updated, stats


def update_bot_count(bot_text: str, count: int) -> str:
    updated, replacements = re.subn(
        r"\d+ проверенн(?:ое|ых) мест(?:о|а)?",
        f"{count} проверенных мест",
        bot_text,
        count=1,
    )
    if replacements != 1:
        raise ValueError("Could not update the place count in bot.py")
    return updated


def main() -> None:
    args = parse_args()
    html = args.html.read_text(encoding="utf-8")
    current = embedded_json(html, "j-db")
    metro_coords = embedded_json(html, "j-mc")
    rows = read_csv(args.csv_path)
    updated, stats = update_database(rows, current, metro_coords)

    new_html = replace_embedded_json(html, "j-db", updated)
    bot_text = args.bot.read_text(encoding="utf-8")
    new_bot_text = update_bot_count(bot_text, len(updated))

    print(
        f"records: {len(current)} -> {len(updated)}; "
        f"matched: {stats['matched']}; moved: {stats['moved']}; new: {stats['new']}"
    )
    print("categories:", dict(sorted(Counter(item["c"] for item in updated).items())))

    if args.dry_run:
        return
    args.html.write_text(new_html, encoding="utf-8")
    args.bot.write_text(new_bot_text, encoding="utf-8")


if __name__ == "__main__":
    main()
