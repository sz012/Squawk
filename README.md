# Squawk

Live ADS-B mini-radar showing air traffic over Poland. A FastAPI backend fetches and caches aircraft positions from the OpenSky Network, a React + Leaflet frontend draws them on a dark map. "Squawk" is the four-digit transponder code that air traffic control assigns to every flight.

(screenshot soon)

## Features

- live aircraft positions over Poland, refreshed every 10 s
- icons rotated to the aircraft's track, with a velocity vector (longer = faster)
- smooth movement between updates
- tooltip with callsign, altitude and speed on hover
- link status: LIVE / STALE (last known data when OpenSky throttles) / NO LINK
- UTC clock and a radar ping on each data refresh

## Run locally

Requirements: Python 3.12+, Node 20+.

Backend:

```bash
cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn main:app --reload --port 8000
```

Frontend (second terminal):

```bash
cd frontend
npm install
npm run dev
```

Anonymous OpenSky access has a small daily quota per IP. When it runs out, the app keeps showing the last known positions with a STALE badge - that is expected, the quota resets around midnight UTC.

## Data & credits

- flight data: [OpenSky Network](https://opensky-network.org/) (non-commercial use)
- map tiles: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, © [CARTO](https://carto.com/attributions)
- font: [B612](https://b612-font.com/) (SIL Open Font License), designed for Airbus cockpit displays
