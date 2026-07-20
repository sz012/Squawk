# Squawk

![CI](https://github.com/sz012/Squawk/actions/workflows/ci.yml/badge.svg)

Live ADS-B mini-radar. A FastAPI backend fetches and caches aircraft positions from adsb.lol, a React + Leaflet frontend draws them on a dark map - move anywhere in the world and the radar follows. "Squawk" is the four-digit transponder code that air traffic control assigns to every flight.

**Live demo - [squawk-inky.vercel.app](https://squawk-inky.vercel.app)** Hosted on free tiers — the backend may take ~30–60 s to wake up on the first visit.

![Squawk radar](docs/radar.png)

## Features

- live aircraft positions refreshed every 10 s - the radar follows the map, move anywhere in the world
- HOME button returns to the Polish sector, the header shows current sector coordinates
- icons rotated to the aircraft's track, with a velocity vector (longer = faster)
- click a plane: airline, route (from -> to), aircraft type, squawk code, altitude, speed, vertical rate
- full flight path drawn from takeoff, extended live while the plane flies
- track switch: current leg or all of the aircraft's flights today
- ground targets filter, hover tooltip, smooth movement between updates
- airport board: live arrivals/departures for WAW/KRK/GDN/KTW
- link status: LIVE / STALE (last known data when the feed is unreachable) / NO LINK
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

No API keys needed. If the data source is unreachable, the app keeps showing last known positions with a STALE badge.

## Data & credits

- live positions and flight tracks: [adsb.lol](https://adsb.lol/) (open community API)
- routes and aircraft info: [adsbdb](https://www.adsbdb.com/)
- map tiles: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, © [CARTO](https://carto.com/attributions)
- font: [B612](https://b612-font.com/) (SIL Open Font License), designed for Airbus cockpit displays
