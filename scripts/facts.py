"""Work out where a coordinate is and find something fun to say about it."""
import json
import math
import urllib.parse
import urllib.request

USER_AGENT = "family-cruise-tracker/1.0 (personal non-commercial project)"
HOME = (50.904, -1.429)  # Southampton

# Checked in order, so smaller seas come before the oceans that contain them.
SEA_AREAS = [
    ("the Solent", 50.6, 50.95, -1.6, -1.0),
    ("the Strait of Gibraltar", 35.8, 36.2, -6.1, -5.3),
    ("the English Channel", 48.6, 51.2, -5.8, 1.8),
    ("the Irish Sea", 51.9, 55.2, -6.5, -2.8),
    ("the Celtic Sea", 48.6, 52.0, -10.0, -5.0),
    ("the North Sea", 51.0, 61.0, -3.0, 9.0),
    ("the Bay of Biscay", 43.3, 48.6, -8.0, 0.0),
    ("the Alboran Sea", 35.0, 37.0, -5.3, -1.0),
    ("the Balearic Sea", 38.0, 42.0, -1.0, 4.5),
    ("the Tyrrhenian Sea", 38.0, 44.0, 9.5, 16.0),
    ("the Adriatic Sea", 40.0, 46.0, 12.0, 20.0),
    ("the Ionian Sea", 35.0, 40.0, 16.0, 22.0),
    ("the Aegean Sea", 35.0, 41.0, 22.0, 28.0),
    ("the Mediterranean Sea", 30.0, 46.0, -5.3, 36.5),
    ("the waters around the Canary Islands", 27.0, 30.0, -19.0, -13.0),
    ("the waters around Madeira", 32.0, 33.7, -18.0, -15.5),
    ("the waters around the Azores", 36.5, 40.0, -32.0, -24.0),
    ("the North Atlantic", 0.0, 70.0, -80.0, 0.0),
]

PLACES = [
    ("Southampton", 50.90, -1.40), ("Cherbourg", 49.64, -1.62), ("Brest", 48.39, -4.49),
    ("A Coruña", 43.37, -8.40), ("Vigo", 42.24, -8.72), ("Porto", 41.15, -8.61),
    ("Lisbon", 38.72, -9.14), ("Cádiz", 36.53, -6.29), ("Gibraltar", 36.14, -5.35),
    ("Málaga", 36.72, -4.42), ("Cartagena", 37.60, -0.99), ("Alicante", 38.35, -0.48),
    ("Valencia", 39.47, -0.38), ("Barcelona", 41.39, 2.17), ("Palma", 39.57, 2.65),
    ("Marseille", 43.30, 5.37), ("Genoa", 44.41, 8.93), ("Rome", 41.90, 12.50),
    ("Naples", 40.85, 14.27), ("Palermo", 38.12, 13.36), ("Valletta", 35.90, 14.51),
    ("Athens", 37.98, 23.73), ("Funchal", 32.65, -16.91), ("Ponta Delgada", 37.74, -25.67),
    ("Santa Cruz de Tenerife", 28.46, -16.25), ("Las Palmas", 28.12, -15.43),
    ("Arrecife", 28.96, -13.55), ("Casablanca", 33.57, -7.59), ("Agadir", 30.43, -9.60),
    ("Tangier", 35.76, -5.83), ("Dublin", 53.35, -6.26), ("Amsterdam", 52.37, 4.90),
]

# Used for same-latitude and far-side-of-the-world comparisons.
WORLD_CITIES = [
    ("New York", 40.71, -74.01), ("Boston", 42.36, -71.06), ("Chicago", 41.88, -87.63),
    ("Toronto", 43.65, -79.38), ("Montreal", 45.50, -73.57), ("Vancouver", 49.28, -123.12),
    ("Calgary", 51.05, -114.07), ("Winnipeg", 49.90, -97.14), ("Seattle", 47.61, -122.33),
    ("San Francisco", 37.77, -122.42), ("Washington, D.C.", 38.91, -77.04),
    ("Los Angeles", 34.05, -118.24), ("Atlanta", 33.75, -84.39), ("Dallas", 32.78, -96.80),
    ("New Orleans", 29.95, -90.07), ("Miami", 25.76, -80.19), ("Houston", 29.76, -95.37),
    ("Beijing", 39.90, 116.41), ("Seoul", 37.57, 126.98), ("Tokyo", 35.68, 139.69),
    ("Shanghai", 31.23, 121.47), ("Delhi", 28.61, 77.21), ("Tehran", 35.69, 51.39),
    ("Baghdad", 33.32, 44.36), ("Kathmandu", 27.72, 85.32), ("Tashkent", 41.30, 69.24),
    ("Vladivostok", 43.12, 131.89), ("Ulaanbaatar", 47.89, 106.91), ("Astana", 51.17, 71.45),
    ("Irkutsk", 52.29, 104.31), ("Cairo", 30.04, 31.24), ("Dubai", 25.20, 55.27),
    ("Auckland", -36.85, 174.76), ("Wellington", -41.29, 174.78), ("Christchurch", -43.53, 172.64),
    ("Dunedin", -45.87, 170.50), ("Sydney", -33.87, 151.21), ("Hobart", -42.88, 147.33),
    ("Suva", -18.14, 178.44), ("Nuku'alofa", -21.14, -175.20), ("Apia", -13.83, -171.76),
    ("Papeete", -17.54, -149.57), ("Santiago", -33.45, -70.67), ("Ushuaia", -54.80, -68.30),
]


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def bearing_word(lat1, lon1, lat2, lon2):
    """Compass direction from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return compass_word(math.degrees(math.atan2(y, x)))


def compass_word(degrees):
    words = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
    return words[round((degrees % 360) / 45) % 8]


def sea_area(lat, lon):
    for name, lat_min, lat_max, lon_min, lon_max in SEA_AREAS:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name
    return "open water"


def nearest(lat, lon, places):
    return min(places, key=lambda p: distance_km(lat, lon, p[1], p[2]))


def describe_location(lat, lon):
    name, plat, plon = nearest(lat, lon, PLACES)
    km = distance_km(lat, lon, plat, plon)
    if km < 15:
        return f"at {name}"
    return f"about {round(km, -1):,.0f} km {bearing_word(plat, plon, lat, lon)} of {name}"


def latitude_twin_fact(lat, lon, day):
    """A far-away city at about the same latitude, or None if none is listed."""
    twins = [c for c in WORLD_CITIES if abs(c[1] - lat) <= 1.5 and abs(c[2] - lon) > 30]
    if not twins:
        return None
    twin = twins[day % len(twins)]
    return f"This far north, they're roughly level with {twin[0]}, even though it's a world away."


def antipode_fact(lat, lon):
    alat, alon = -lat, lon + 180 if lon <= 0 else lon - 180
    name, plat, plon = nearest(alat, alon, WORLD_CITIES)
    km = distance_km(alat, alon, plat, plon)
    return (f"Drill straight through the Earth from here and you'd surface at "
            f"{abs(alat):.1f}°{'S' if alat < 0 else 'N'}, {abs(alon):.1f}°{'W' if alon < 0 else 'E'}, "
            f"about {round(km, -1):,.0f} km from {name}.")


def spin_fact(lat):
    mph = 1037.6 * math.cos(math.radians(lat))
    return f"At this latitude, the Earth's spin carries the ship east at about {round(mph, -1):,.0f} mph, whatever the captain is doing."


def sun_fact(lon):
    minutes = round((lon - HOME[1]) * 4)
    if abs(minutes) < 5:
        return "The sun reaches its highest point here at almost the same moment as in Southampton."
    when = "before" if minutes > 0 else "after"
    return f"The sun reaches its highest point here about {abs(minutes)} minutes {when} it does in Southampton."


def _get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def depth_fact(lat, lon):
    """Seabed depth from the GEBCO dataset. Returns None when on land or unavailable."""
    try:
        data = _get_json(f"https://api.opentopodata.org/v1/gebco2020?locations={lat:.4f},{lon:.4f}")
        elevation = data["results"][0]["elevation"]
    except Exception as error:
        print(f"::notice::Depth lookup skipped: {error}")
        return None
    if elevation is None or elevation > -20:
        return None
    depth = round(-elevation)
    towers = depth / 330
    comparison = f", which is about {towers:.1f} Eiffel Towers stacked up" if towers >= 1 else ""
    return f"The seabed is roughly {depth:,} m below the ship{comparison}."


def wikipedia_fact(lat, lon):
    """Something notable within 10 km, from Wikipedia. Returns None out at sea."""
    try:
        query = urllib.parse.urlencode({
            "action": "query", "list": "geosearch", "gscoord": f"{lat:.4f}|{lon:.4f}",
            "gsradius": 10000, "gslimit": 1, "format": "json",
        })
        hits = _get_json(f"https://en.wikipedia.org/w/api.php?{query}")["query"]["geosearch"]
        if not hits:
            return None
        title = urllib.parse.quote(hits[0]["title"].replace(" ", "_"), safe="")
        page = _get_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}")
        extract = page["extract"].split(". ")[0].rstrip(".")
        return {"text": f"Nearby: {extract}.", "url": page["content_urls"]["desktop"]["page"]}
    except Exception as error:
        print(f"::notice::Wikipedia lookup skipped: {error}")
        return None


def build_facts(lat, lon, day, lookup=True):
    """All facts for a position. `day` rotates the choice so the email changes daily."""
    facts = [{"text": spin_fact(lat)}, {"text": sun_fact(lon)}, {"text": antipode_fact(lat, lon)}]
    twin = latitude_twin_fact(lat, lon, day)
    if twin:
        facts.append({"text": twin})
    nearby = None
    if lookup:
        depth = depth_fact(lat, lon)
        if depth:
            facts.append({"text": depth})
        nearby = wikipedia_fact(lat, lon)
    featured = nearby or facts[day % len(facts)]
    return {"featured": featured, "all": facts}
