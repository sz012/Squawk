import asyncio
import logging
import os
import time

import httpx
from fastapi import FastAPI
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
async def get_track(icao24: str):
    #pelna sciezka lotu od startu, cache 60s
    now = time.time()
    cached = _track_cache.get(icao24)
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
    leg = _current_leg(payload.get("trace") or [])
    path = [[p[1], p[2]] for p in leg if p[1] is not None and p[2] is not None]
    path = path[-2000:]
    result = {"path": path}
    if len(_track_cache) > 300:
        _track_cache.clear()
    _track_cache[icao24] = (now, result)
    return result


@app.get("/flightinfo/{icao24}/{callsign}")
async def get_flight_info(icao24: str, callsign: str):
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
