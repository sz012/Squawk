import asyncio
import logging
import math
import os
import time

import httpx
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware

#./.venv/bin/uvicorn main:app --reload --port 8000
#http://localhost:8000/flights / http://localhost:8000/docs

#logi trafiaja do wyjscia uvicorna (widoczne tez w panelu hostingu)
logger = logging.getLogger("uvicorn.error")

#pozycje na zywo - otwarte api adsb.lol (okrag: srodek PL, promien 250 mil morskich)
STATES_URL = "https://api.adsb.lol/v2/lat/52.1/lon/19.4/dist/250"
#pelna sciezka lotu - endpoint tar1090 na infrastrukturze adsb.lol
TRACE_URL = "https://globe.adsb.lol/data/traces/{suffix}/trace_full_{icao24}.json"
#spolecznosciowa baza tras i samolotow (bez klucza)
ADSBDB_URL = "https://api.adsbdb.com/v0"

#ile sekund przed odpytaniem API ponownie
CACHE_TTL = 6

#przeliczniki jednostek lotniczych na metryczne
FT_TO_M = 0.3048
KT_TO_MS = 0.514444
FTMIN_TO_MS = 0.00508  #stopy/min -> m/s

app = FastAPI(title="Squawk API")

#dozwolone originy - lokalnie porty vite, na produkcji domena frontendu ze zmiennej env
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://localhost:5175",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

_cache = {"time": 0.0, "data": []}
_track_cache = {}  #icao24 -> (czas, wynik)
_info_cache = {}  #icao24:callsign -> (czas, wynik)
_route_cache = {}  #callsign -> (czas, trasa)
_board_cache = {}  #kod lotniska -> (czas, tablica)

#lotniska obslugiwane przez tablice
AIRPORTS = {
    "WAW": {"name": "Warszawa Chopin", "lat": 52.1657, "lon": 20.9671},
    "KRK": {"name": "Krakow Balice", "lat": 50.0777, "lon": 19.7848},
    "GDN": {"name": "Gdansk Rebiechowo", "lat": 54.3776, "lon": 18.4662},
    "KTW": {"name": "Katowice Pyrzowice", "lat": 50.4743, "lon": 19.0800},
}


def _http_client() -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(retries=2, local_address="0.0.0.0")
    return httpx.AsyncClient(
        timeout=httpx.Timeout(15, connect=10),
        transport=transport,
        follow_redirects=True,
    )


def _parse_aircraft(ac: dict) -> dict:
    alt = ac.get("alt_baro")
    on_ground = alt == "ground"
    callsign = (ac.get("flight") or "").strip()
    return {
        "icao24": ac.get("hex"),  #unikalny id transpondera
        "callsign": callsign or None,  #znak wywolawczy lotu
        "last_contact": int(time.time() - ac.get("seen", 0)),  #unix ts ostatniego sygnalu
        "lon": ac.get("lon"),
        "lat": ac.get("lat"),
        "altitude": None if on_ground or alt is None else round(alt * FT_TO_M, 1),
        "on_ground": on_ground,
        "velocity": round(ac["gs"] * KT_TO_MS, 1) if ac.get("gs") is not None else None,  #m/s
        "track": ac.get("track"),  #kurs w stopniach 0=polnoc
        "vertical_rate": round(ac["baro_rate"] * FTMIN_TO_MS, 1) if ac.get("baro_rate") is not None else None,
        "squawk": ac.get("squawk"),  #kod transpondera
    }


async def _fetch_flights() -> list:
    #pobiera swieze pozycje z adsb.lol
    async with _http_client() as client:
        response = await client.get(STATES_URL)
        response.raise_for_status()
        payload = response.json()

    aircraft = payload.get("ac") or []
    #odsiewam wpisy bez pozycji
    flights = [
        _parse_aircraft(a)
        for a in aircraft
        if a.get("lat") is not None and a.get("lon") is not None and not str(a.get("hex", "")).startswith("~")
    ]
    return flights


@app.get("/flights")
async def get_flights():
    #zwraca liste samolotow
    now = time.time()
    if now - _cache["time"] < CACHE_TTL and _cache["data"]:
        return {"cached": True, "count": len(_cache["data"]), "flights": _cache["data"]}

    try:
        flights = await _fetch_flights()
    except httpx.HTTPError as exc:
        logger.warning("zrodlo pozycji niedostepne: %r", exc)
        return {"cached": True, "stale": True, "count": len(_cache["data"]), "flights": _cache["data"]}

    _cache["time"] = now
    _cache["data"] = flights
    return {"cached": False, "count": len(flights), "flights": flights}


def _current_leg(points: list) -> list:
    #trace_full to cala dzisiejsza historia samolotu (wiele rejsow) - wycinam niepotrzebny odcinek
    cut = 0
    prev_t = None
    seen_air = False
    for i in range(len(points) - 1, -1, -1):
        p = points[i]
        if prev_t is not None and prev_t - p[0] > 1800:
            cut = i + 1
            break
        on_ground = p[3] == "ground"
        if on_ground and seen_air:
            cut = i
            break
        if not on_ground:
            seen_air = True
        prev_t = p[0]
    return points[cut:]


@app.get("/track/{icao24}")
async def get_track(
    icao24: str = Path(pattern=r"^[0-9a-fA-F]{6}$"),
    scope: str = Query("leg", pattern=r"^(leg|day)$"),  #leg - biezacy odcinek, day - wszystkie dzisiejsze przeloty
):
    #sciezka lotu, cache 60s
    icao24 = icao24.lower()
    now = time.time()
    key = f"{icao24}:{scope}"
    cached = _track_cache.get(key)
    if cached and now - cached[0] < 60:
        return cached[1]

    url = TRACE_URL.format(suffix=icao24[-2:], icao24=icao24)
    try:
        async with _http_client() as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        #brak sciezki to nie blad krytyczny - frontend uzyje wlasnej historii
        logger.warning("trace niedostepny dla %s: %r", icao24, exc)
        return {"path": []}

    #punkt trace - [offset_s, lat, lon, wysokosc, predkosc, ...]
    points = payload.get("trace") or []
    if scope == "leg":
        points = _current_leg(points)
    path = [[p[1], p[2]] for p in points if p[1] is not None and p[2] is not None]
    if len(path) > 2000:
        step = len(path) // 2000 + 1
        path = path[::step]
    result = {"path": path}
    if len(_track_cache) > 300:
        _track_cache.clear()
    _track_cache[key] = (now, result)
    return result


@app.get("/flightinfo/{icao24}/{callsign}")
async def get_flight_info(
    icao24: str = Path(pattern=r"^[0-9a-fA-F]{6}$"),
    callsign: str = Path(pattern=r"^[A-Za-z0-9]{1,8}$"),
):
    #wzbogacenie - linia lotnicza, trasa skad-dokad, typ maszyny (adsbdb.com)
    now = time.time()
    key = f"{icao24}:{callsign}"
    cached = _info_cache.get(key)
    if cached and now - cached[0] < 6 * 3600:
        return cached[1]

    route = None
    aircraft = None
    async with _http_client() as client:
        r_route, r_ac = await asyncio.gather(
            client.get(f"{ADSBDB_URL}/callsign/{callsign}"),
            client.get(f"{ADSBDB_URL}/aircraft/{icao24}"),
            return_exceptions=True,
        )

    if not isinstance(r_route, BaseException) and r_route.status_code == 200:
        data = r_route.json().get("response")
        if isinstance(data, dict) and data.get("flightroute"):
            fr = data["flightroute"]
            airline = fr.get("airline") or {}
            origin = fr.get("origin") or {}
            dest = fr.get("destination") or {}
            route = {
                "airline": {"name": airline.get("name"), "icao": airline.get("icao")},
                "origin": {"iata": origin.get("iata_code"), "city": origin.get("municipality")},
                "destination": {"iata": dest.get("iata_code"), "city": dest.get("municipality")},
            }

    if not isinstance(r_ac, BaseException) and r_ac.status_code == 200:
        data = r_ac.json().get("response")
        if isinstance(data, dict) and data.get("aircraft"):
            ac = data["aircraft"]
            aircraft = {"type": ac.get("icao_type") or ac.get("type"), "registration": ac.get("registration")}

    result = {"route": route, "aircraft": aircraft}
    if len(_info_cache) > 500:
        _info_cache.clear()
    _info_cache[key] = (now, result)
    return result


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


async def _route_for(client: httpx.AsyncClient, sem: asyncio.Semaphore, callsign: str):
    cached = _route_cache.get(callsign)
    if cached and time.time() - cached[0] < 6 * 3600:
        return cached[1]

    async with sem:
        try:
            r = await client.get(f"{ADSBDB_URL}/callsign/{callsign}")
        except httpx.HTTPError:
            return None

    route = None
    if r.status_code == 200:
        data = r.json().get("response")
        if isinstance(data, dict) and data.get("flightroute"):
            fr = data["flightroute"]
            airline = fr.get("airline") or {}
            origin = fr.get("origin") or {}
            dest = fr.get("destination") or {}
            route = {
                "airline": airline.get("name"),
                "origin": {"iata": origin.get("iata_code"), "city": origin.get("municipality")},
                "destination": {"iata": dest.get("iata_code"), "city": dest.get("municipality")},
            }
    if len(_route_cache) > 1000:
        _route_cache.clear()
    _route_cache[callsign] = (time.time(), route)
    return route


@app.get("/board/{airport}")
async def get_board(airport: str = Path(pattern=r"^[A-Z]{3}$")):
    #tablica lotniska liczona z zywego ruchu + tras adsbdb, cache 30s
    ap = AIRPORTS.get(airport)
    if not ap:
        raise HTTPException(status_code=404, detail="nieznane lotnisko")

    now = time.time()
    cached = _board_cache.get(airport)
    if cached and now - cached[0] < 30:
        return cached[1]

    #biezace pozycje - z cache /flights albo swieze
    if now - _cache["time"] < CACHE_TTL and _cache["data"]:
        flights = _cache["data"]
    else:
        try:
            flights = await _fetch_flights()
            _cache["time"] = now
            _cache["data"] = flights
        except httpx.HTTPError:
            flights = _cache["data"]

    candidates = []
    for f in flights:
        if not f["callsign"]:
            continue
        dist = _haversine_km(f["lat"], f["lon"], ap["lat"], ap["lon"])
        if f["on_ground"]:
            if dist < 5:
                candidates.append((f, dist))
            continue
        toward = False
        if f["track"] is not None:
            brg = _bearing_deg(f["lat"], f["lon"], ap["lat"], ap["lon"])
            toward = abs((f["track"] - brg + 180) % 360 - 180) <= 45
        if dist < 600 and (toward or dist < 120):
            candidates.append((f, dist))

    sem = asyncio.Semaphore(8)
    async with _http_client() as client:
        routes = await asyncio.gather(*[_route_for(client, sem, f["callsign"]) for f, _ in candidates])

    arrivals = []
    departures = []
    for (f, dist), route in zip(candidates, routes):
        if not route:
            continue
        base = {
            "icao24": f["icao24"],
            "callsign": f["callsign"],
            "airline": route["airline"],
            "dist_km": round(dist),
        }
        if route["destination"]["iata"] == airport:
            if f["on_ground"]:
                arrivals.append({**base, "from": route["origin"], "eta_min": 0, "landed": True})
            else:
                eta = None
                if f["velocity"] and f["velocity"] > 50:
                    eta = round(dist * 1000 / f["velocity"] / 60)
                arrivals.append({**base, "from": route["origin"], "eta_min": eta, "landed": False})
        if route["origin"]["iata"] == airport:
            if f["on_ground"]:
                departures.append({**base, "to": route["destination"], "status": "GND"})
            elif dist < 300:
                departures.append({**base, "to": route["destination"], "status": "OUT"})

    arrivals.sort(key=lambda x: (x["landed"], x["eta_min"] is None, x["eta_min"] or 0))
    departures.sort(key=lambda x: x["status"] != "OUT")

    result = {"airport": airport, "name": ap["name"], "arrivals": arrivals, "departures": departures}
    _board_cache[airport] = (now, result)
    return result
