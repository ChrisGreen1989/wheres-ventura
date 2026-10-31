import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect
import facts
import send_update
from websockets.asyncio.server import serve

MMSI = "310562000"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def report(mmsi=MMSI, lat=45.5, lon=-5.5, **fields):
    position = {"Sog": 18.5, "Cog": 200.0, "TrueHeading": 205, "Valid": True, **fields}
    return {"MessageType": "PositionReport", "MetaData": {"MMSI": int(mmsi), "Latitude": lat, "Longitude": lon},
            "Message": {"PositionReport": position}}


class ParsePosition(unittest.TestCase):
    def test_reads_a_good_report(self):
        fix = collect.parse_position(report(), MMSI)
        self.assertEqual((fix["lat"], fix["lon"], fix["speed_knots"], fix["heading"]), (45.5, -5.5, 18.5, 205))

    def test_rejects_other_ships_and_bad_positions(self):
        self.assertIsNone(collect.parse_position(report(mmsi="123456789"), MMSI))
        self.assertIsNone(collect.parse_position(report(lat=91), MMSI))
        self.assertIsNone(collect.parse_position(report(Valid=False), MMSI))

    def test_uses_course_when_heading_is_unavailable(self):
        self.assertEqual(collect.parse_position(report(TrueHeading=511), MMSI)["heading"], 200.0)
        fix = collect.parse_position(report(TrueHeading=511, Cog=360, Sog=102.3), MMSI)
        self.assertIsNone(fix["heading"])
        self.assertIsNone(fix["speed_knots"])


class Track(unittest.TestCase):
    def point(self, lat, time):
        return {"lat": lat, "lon": 0.0, "time": time, "speed_knots": 1, "heading": 0}

    def test_skips_small_moves_but_keeps_real_ones_and_long_gaps(self):
        track = collect.add_to_track([], self.point(50.0, "2026-11-01T00:00:00+00:00"))
        self.assertEqual(len(collect.add_to_track(track, self.point(50.001, "2026-11-01T00:30:00+00:00"))), 1)
        self.assertEqual(len(collect.add_to_track(track, self.point(50.1, "2026-11-01T00:30:00+00:00"))), 2)
        self.assertEqual(len(collect.add_to_track(track, self.point(50.0, "2026-11-01T07:00:00+00:00"))), 2)


class Facts(unittest.TestCase):
    def test_sea_areas(self):
        self.assertEqual(facts.sea_area(50.0, -2.0), "the English Channel")
        self.assertEqual(facts.sea_area(45.5, -5.5), "the Bay of Biscay")
        self.assertEqual(facts.sea_area(38.0, 5.0), "the Mediterranean Sea")
        self.assertEqual(facts.sea_area(35.0, -30.0), "the North Atlantic")

    def test_distance_and_direction(self):
        self.assertAlmostEqual(facts.distance_km(0, 0, 0, 1), 111.2, delta=0.2)
        self.assertEqual(facts.bearing_word(42.24, -8.72, 40.0, -8.72), "south")
        self.assertEqual(facts.compass_word(359), "north")

    def test_antipode_of_southampton_is_south_pacific_near_new_zealand(self):
        text = facts.antipode_fact(50.9, -1.4)
        self.assertIn("50.9°S, 178.6°E", text)
        self.assertIn("Dunedin", text)

    def test_sun_direction(self):
        self.assertIn("after", facts.sun_fact(-16))
        self.assertIn("before", facts.sun_fact(14))

    def test_fact_rotates_by_day(self):
        days = {facts.build_facts(45.5, -5.5, d, lookup=False)["featured"]["text"] for d in range(4)}
        self.assertGreater(len(days), 1)


class Email(unittest.TestCase):
    NOW = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
    LATEST = {"position": {"lat": 45.5, "lon": -5.5, "speed_knots": 18.5, "heading": 205,
                           "time": "2026-11-02T07:30:00+00:00"},
              "location": "about 300 km north of A Coruña", "sea": "the Bay of Biscay", "home_km": 700,
              "facts": {"featured": {"text": "Fish <3 tides."}}, "error": None}

    def test_fresh_position(self):
        subject, text, body = send_update.build_email(CONFIG, self.LATEST, self.NOW.date(), self.NOW, "https://x.test/")
        self.assertIn("Ventura is about 300 km", subject)
        self.assertIn("Right now", text)
        self.assertIn("11 days until home", text)
        self.assertIn("Fish &lt;3 tides.", body)

    def test_stale_position_says_so(self):
        now = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)
        subject, text, _ = send_update.build_email(CONFIG, self.LATEST, now.date(), now, "")
        self.assertIn("last seen", subject)
        self.assertIn("24 hours ago", text)

    def test_no_position_and_error_reported(self):
        subject, text, _ = send_update.build_email(CONFIG, {"error": "bad key"}, self.NOW.date(), self.NOW, "")
        self.assertIn("no position yet", subject)
        self.assertIn("Tracker problem: bad key", text)


class EndToEnd(unittest.TestCase):
    """Runs the real websocket client against a local stand-in for AISStream."""

    def run_server(self, handler, seconds=5):
        async def scenario():
            async with serve(handler, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                collect.AIS_URL = f"ws://127.0.0.1:{port}"
                return await collect.listen("test-key", MMSI, seconds)
        return asyncio.run(scenario())

    def test_subscribes_and_finds_the_ship_among_others(self):
        received = {}

        async def handler(socket):
            received.update(json.loads(await socket.recv()))
            await socket.send(json.dumps(report(mmsi="123456789")))
            await socket.send(json.dumps(report(lat=44.0)))
            await socket.wait_closed()

        fix = self.run_server(handler)
        self.assertEqual(fix["lat"], 44.0)
        self.assertEqual(received["FiltersShipMMSI"], [MMSI])
        self.assertEqual(received["APIKey"], "test-key")

    def test_silence_is_not_an_error(self):
        async def handler(socket):
            await socket.wait_closed()
        self.assertIsNone(self.run_server(handler, seconds=1))

    def test_closed_connection_and_error_message_are_errors(self):
        async def closes(socket):
            await socket.recv()

        async def complains(socket):
            await socket.recv()
            await socket.send(json.dumps({"error": "Api Key Is Not Valid"}))
            await socket.wait_closed()

        with self.assertRaises(Exception):
            self.run_server(closes)
        with self.assertRaisesRegex(RuntimeError, "Not Valid"):
            self.run_server(complains)

    def test_files_keep_last_position_when_no_new_fix(self):
        with tempfile.TemporaryDirectory() as folder:
            collect.DATA_DIR = Path(folder)
            fix = collect.parse_position(report(), MMSI)
            collect.update_files(CONFIG, fix, None, date(2026, 11, 2), lookup=False)
            latest = collect.update_files(CONFIG, None, None, date(2026, 11, 2), lookup=False)
            self.assertEqual(latest["position"]["lat"], 45.5)
            self.assertEqual(len(json.loads((Path(folder) / "track.json").read_text(encoding="utf-8"))), 1)


if __name__ == "__main__":
    unittest.main()
