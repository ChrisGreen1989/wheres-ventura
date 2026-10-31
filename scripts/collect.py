"""Listen briefly to AISStream for the ship's position and update the site's data files."""
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

import facts

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "docs" / "data"))
AIS_URL = os.environ.get("AIS_URL", "wss://stream.aisstream.io/v0/stream")
LISTEN_SECONDS = int(os.environ.get("LISTEN_SECONDS", "420"))
MIN_MOVE_KM = 0.5
MAX_GAP_SECONDS = 6 * 3600


def parse_position(message, mmsi):
    """Turn any AISStream message into a fix, or None if it has no usable position for this ship.

    Only position reports carry speed and heading, but every message type has coordinates.
    """
    meta = message.get("MetaData", {})
    report = message.get("Message", {}).get("PositionReport", {})
    if str(meta.get("MMSI")) != str(mmsi) or report.get("Valid") is False:
        return None
    lat, lon = meta.get("Latitude"), meta.get("Longitude")
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    # AIS uses these out-of-range values to mean "not available".
    speed = report.get("Sog")
    heading = report.get("TrueHeading")
    course = report.get("Cog")
    if heading is None or heading >= 360:
        heading = course if course is not None and course < 360 else None
    return {
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "speed_knots": speed if speed is not None and speed < 102.3 else None,
        "heading": heading,
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


async def listen(api_key, mmsi, seconds):
    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": [[[-90, -180], [90, 180]]],
    }
    heard = 0
    try:
        async with asyncio.timeout(seconds):
            while True:
                heard_before = heard
                try:
                    async with connect(AIS_URL, open_timeout=20) as socket:
                        await socket.send(json.dumps(subscription))
                        async for raw in socket:
                            message = json.loads(raw)
                            if "error" in message:
                                raise RuntimeError(f"AISStream said: {message['error']}")
                            heard += 1
                            # Filter here, because the ship filter on AISStream's side returned nothing.
                            if str(message.get("MetaData", {}).get("MMSI")) != str(mmsi):
                                continue
                            fix = parse_position(message, mmsi)
                            print(f"Received {message.get('MessageType')} after {heard} messages: {fix}")
                            if fix:
                                return fix
                except ConnectionClosed:
                    pass
                # A drop after some data is routine on a stream this busy, so carry on listening.
                if heard == heard_before:
                    raise RuntimeError("AISStream closed the connection. Check the API key.")
                print(f"Connection dropped after {heard} messages, reconnecting.")
    except TimeoutError:
        print(f"Heard {heard} messages from other ships, none usable from this one.")
        return None  # Normal when the ship is out of range of AIS receivers.


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
    api_key = os.environ.get("AISSTREAM_API_KEY")
    if not api_key:
        sys.exit("AISSTREAM_API_KEY is not set.")

    fix, error = None, None
    try:
        fix = asyncio.run(listen(api_key, config["mmsi"], LISTEN_SECONDS))
    except Exception as problem:
        error = str(problem).replace(api_key, "***")
        print(f"::warning::{error}")
    print(f"Position: {fix}" if fix else "No new position this time.")
    update_files(config, fix, error, today)


if __name__ == "__main__":
    main()
