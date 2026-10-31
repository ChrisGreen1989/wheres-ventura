"""Ask VesselAPI for the ship's latest position and update the site's data files."""
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import facts

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "docs" / "data"))
API_URL = os.environ.get("VESSEL_API_URL", "https://api.vesselapi.com/v1")
MIN_MOVE_KM = 0.5
MAX_GAP_SECONDS = 6 * 3600


def parse_position(payload, mmsi):
    """Turn a VesselAPI response into a fix, or None if it has no usable position for this ship."""
    position = payload.get("vesselPosition") or {}
    if str(position.get("mmsi")) != str(mmsi) or position.get("suspected_glitch"):
        return None
    lat, lon, seen = position.get("latitude"), position.get("longitude"), position.get("timestamp")
    if lat is None or lon is None or not seen or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    # AIS uses these out-of-range values to mean "not available".
    speed = position.get("sog")
    heading = position.get("heading")
    course = position.get("cog")
    if heading is None or heading >= 360:
        heading = course if course is not None and course < 360 else None
    return {
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "speed_knots": speed if speed is not None and speed < 102.3 else None,
        "heading": heading,
        # The time the ship reported this, which can be hours before we asked.
        "time": datetime.fromisoformat(seen).astimezone(timezone.utc).isoformat(timespec="seconds"),
    }


def fetch_position(api_key, mmsi):
    request = Request(
        f"{API_URL}/vessel/{mmsi}/position?filter.idType=mmsi",
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": "wheres-ventura"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as problem:
        if problem.code == 404:
            print("VesselAPI has no position from the last 80 hours.")
            return None  # Normal when the ship is out of range of AIS receivers.
        raise RuntimeError(f"VesselAPI answered with HTTP {problem.code}.")
    fix = parse_position(payload, mmsi)
    print(f"Reported position: {fix}")
    return fix


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def add_to_track(track, fix):
    """Keep a point only if the ship moved or a long time has passed, so the file stays small."""
    if track:
        last = track[-1]
        moved = facts.distance_km(last["lat"], last["lon"], fix["lat"], fix["lon"])
        gap = (datetime.fromisoformat(fix["time"]) - datetime.fromisoformat(last["time"])).total_seconds()
        if moved < MIN_MOVE_KM and gap < MAX_GAP_SECONDS:
            return track
    return track + [{k: fix[k] for k in ("lat", "lon", "time")}]


def track_length_km(track):
    return sum(facts.distance_km(a["lat"], a["lon"], b["lat"], b["lon"]) for a, b in zip(track, track[1:]))


def update_files(config, fix, error, today, lookup=True):
    latest_path, track_path = DATA_DIR / "latest.json", DATA_DIR / "track.json"
    latest = load_json(latest_path, {})
    track = load_json(track_path, [])
    latest.update({
        "ship": config["ship_name"],
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error": error,
    })
    if fix:
        track = add_to_track(track, fix)
        save_json(track_path, track)
        latest.update({
            "position": fix,
            "location": facts.describe_location(fix["lat"], fix["lon"]),
            "sea": facts.sea_area(fix["lat"], fix["lon"]),
            "home_km": round(facts.distance_km(fix["lat"], fix["lon"], *facts.HOME)),
            "sailed_km": round(track_length_km(track)),
            "facts": facts.build_facts(fix["lat"], fix["lon"], today.toordinal(), lookup),
        })
    save_json(latest_path, latest)
    return latest


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc).date()
    if not date.fromisoformat(config["start_date"]) <= today <= date.fromisoformat(config["end_date"]):
        print("Outside the cruise dates, so there's nothing to collect.")
        return
    api_key = os.environ.get("VESSELAPI_KEY")
    if not api_key:
        sys.exit("VESSELAPI_KEY is not set.")

    fix, error = None, None
    try:
        fix = fetch_position(api_key, config["mmsi"])
    except Exception as problem:
        error = str(problem).replace(api_key, "***")
        print(f"::warning::{error}")
    print(f"Position: {fix}" if fix else "No new position this time.")
    update_files(config, fix, error, today)


if __name__ == "__main__":
    main()
