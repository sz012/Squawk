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
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_cache = {"time": 0.0, "data": []}
_token = {"value": None, "expires": 0.0}


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
