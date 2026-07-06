import asyncio
import os
import time

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

#./.venv/bin/uvicorn main:app --reload --port 8000
#http://localhost:8000/flights / http://localhost:8000/docs

load_dotenv()  #wczytuje backend/.env jesli istnieje

#surowe stany sledzonych samolotow
OPENSKY_URL = "https://opensky-network.org/api/states/all"
#pelna sciezka trwajacego lotu
TRACK_URL = "https://opensky-network.org/api/tracks/all"
#spolecznosciowa baza tras i samolotow (bez klucza)
ADSBDB_URL = "https://api.adsbdb.com/v0"
#endpoint tokenow OAuth2 dla zarejestrowanych klientow API
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"

#jesli brak kluczy to mniejszy limit bo dzialanie anonimowo
CLIENT_ID = os.getenv("OPENSKY_CLIENT_ID")
CLIENT_SECRET = os.getenv("OPENSKY_CLIENT_SECRET")

#region Polska
DEFAULT_BBOX = {
    "lamin": 49.0,  #min poludnie
    "lomin": 14.1,  #min zachod
    "lamax": 54.9,  #max polnoc
    "lomax": 24.2,  #max wschod
}

#ile sekund przed odpytaniem API ponownie
#OpenSky ma limity dla anonimowych
CACHE_TTL = 6

app = FastAPI(title="Squawk API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5175"],  #porty zapasowe vite
    allow_methods=["GET"],
    allow_headers=["*"],
)

_cache = {"time": 0.0, "data": []}
_token = {"value": None, "expires": 0.0}
_track_cache = {}  #icao24 -> (czas, wynik)
_info_cache = {}  #icao24:callsign -> (czas, wynik)


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


def _parse_state(state: list) -> dict:
    #zamiana na slownik listy wartosci z OpenSky
    callsign = state[1]
    return {
        "icao24": state[0],  #unikalny id transpondera
        "callsign": callsign.strip() if callsign else None,  #znak wywolawczy lotu
        "country": state[2],  #kraj rejestracji
        "last_contact": state[4],  #unix ts ostatniego sygnalu
        "lon": state[5],  #dlugosc geograficzna
        "lat": state[6],  #szerokosc geograficzna
        "altitude": state[7],  #wysokosc barometryczna w metrach
        "on_ground": state[8],  #czy samolot jest na ziemi
        "velocity": state[9],  #predkosc nad ziemia w m/s
        "track": state[10],  #kurs w stopniach 0=polnoc
        "vertical_rate": state[11],  #m/s, ujemne = opada
        "squawk": state[14],  #kod transpondera
    }


async def _fetch_flights() -> list:
    #pobiera swieze dane z OpenSky
    async with httpx.AsyncClient(timeout=15) as client:
        token = await _get_token(client)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = await client.get(OPENSKY_URL, params=DEFAULT_BBOX, headers=headers)
        response.raise_for_status()
        payload = response.json()

    states = payload.get("states") or []

    #odsiewam samoloty bez pozycji
    flights = [_parse_state(s) for s in states if s[5] is not None and s[6] is not None]
    return flights


@app.get("/flights")
async def get_flights():
    #zwraca liste samolotow
    now = time.time()
    if now - _cache["time"] < CACHE_TTL and _cache["data"]:
        return {"cached": True, "count": len(_cache["data"]), "flights": _cache["data"]}

    try:
        flights = await _fetch_flights()
    except httpx.HTTPError:
        #opensky nie odpowiada - ostatnie znane dane zamiast bledu
        return {"cached": True, "stale": True, "count": len(_cache["data"]), "flights": _cache["data"]}

    _cache["time"] = now
    _cache["data"] = flights
    return {"cached": False, "count": len(flights), "flights": flights}


@app.get("/track/{icao24}")
async def get_track(icao24: str):
    #pelna sciezka lotu od startu wg OpenSky, cache 60s
    now = time.time()
    cached = _track_cache.get(icao24)
    if cached and now - cached[0] < 60:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token = await _get_token(client)
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            response = await client.get(TRACK_URL, params={"icao24": icao24, "time": 0}, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError:
        #brak sciezki to nie blad krytyczny - frontend uzyje wlasnej historii
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
    async with httpx.AsyncClient(timeout=10) as client:
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
