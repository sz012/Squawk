import asyncio
import logging
import os
import time

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

#./.venv/bin/uvicorn main:app --reload --port 8000
#http://localhost:8000/flights / http://localhost:8000/docs

load_dotenv()  #wczytuje backend/.env jesli istnieje

#logi trafiaja do wyjscia uvicorna (widoczne tez w panelu hostingu)
logger = logging.getLogger("uvicorn.error")

#pozycje na zywo - otwarte api adsb.lol (okrag: srodek PL, promien 250 mil morskich)
#OpenSky blokuje IP duzych chmur, dlatego stany nie ida z OpenSky
STATES_URL = "https://api.adsb.lol/v2/lat/52.1/lon/19.4/dist/250"
#pelna sciezka trwajacego lotu
TRACK_URL = "https://opensky-network.org/api/tracks/all"
#spolecznosciowa baza tras i samolotow (bez klucza)
ADSBDB_URL = "https://api.adsbdb.com/v0"
#endpoint tokenow OAuth2 dla zarejestrowanych klientow API
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"

#klucze OpenSky - opcjonalne, potrzebne tylko do pelnej sciezki lotu (/track)
CLIENT_ID = os.getenv("OPENSKY_CLIENT_ID")
CLIENT_SECRET = os.getenv("OPENSKY_CLIENT_SECRET")

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
_token = {"value": None, "expires": 0.0}
_track_cache = {}  #icao24 -> (czas, wynik)
_info_cache = {}  #icao24:callsign -> (czas, wynik)


def _http_client() -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(retries=2, local_address="0.0.0.0")
    return httpx.AsyncClient(timeout=httpx.Timeout(15, connect=10), transport=transport)

async def _get_token(client: httpx.AsyncClient):
    #zwraca wazny token albo None gdy brak kluczy
    if not CLIENT_ID or not CLIENT_SECRET:
        return None
    now = time.time()
    if _token["value"] and now < _token["expires"] - 60:
        return _token["value"]

    response = await client.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    response.raise_for_status()
    payload = response.json()
    _token["value"] = payload["access_token"]
    _token["expires"] = now + payload.get("expires_in", 1800)
    return _token["value"]


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
        logger.warning("OpenSky niedostepne: %r", exc)
        return {"cached": True, "stale": True, "count": len(_cache["data"]), "flights": _cache["data"]}

    _cache["time"] = now
    _cache["data"] = flights
    return {"cached": False, "count": len(flights), "flights": flights}


@app.get("/debug")
async def debug_connectivity():
    #TYMCZASOWA diagnostyka polaczen wychodzacych z serwera - do usuniecia po deployu
    targets = [
        ("auth_opensky", TOKEN_URL),
        ("api_opensky", "https://opensky-network.org/api/states/all?lamin=52&lomin=19&lamax=52.1&lomax=19.1"),
        ("adsbdb", f"{ADSBDB_URL}/callsign/LOT1"),
        ("adsb_lol", "https://api.adsb.lol/v2/lat/52.1/lon/19.4/dist/50"),
        ("google", "https://www.google.com"),
    ]
    results = {}
    for name, url in targets:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=5)) as client:
                r = await client.get(url)
            results[name] = f"ok {r.status_code}"
        except Exception as exc:
            results[name] = f"BLAD {exc!r}"
    return results


@app.get("/track/{icao24}")
async def get_track(icao24: str):
    #pelna sciezka lotu od startu wg OpenSky, cache 60s
    now = time.time()
    cached = _track_cache.get(icao24)
    if cached and now - cached[0] < 60:
        return cached[1]

    try:
        async with _http_client() as client:
            token = await _get_token(client)
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            response = await client.get(TRACK_URL, params={"icao24": icao24, "time": 0}, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        #brak sciezki to nie blad krytyczny - frontend uzyje wlasnej historii
        logger.warning("OpenSky tracks niedostepne dla %s: %r", icao24, exc)
        return {"path": []}

    #punkt sciezki - [czas, lat, lon, wysokosc, kurs, on_ground]
    path = [[p[1], p[2]] for p in (payload.get("path") or []) if p[1] is not None and p[2] is not None]
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
