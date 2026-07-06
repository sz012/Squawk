//komunikacja z backendem FastAPI
//adres do nadpisania zmienna VITE_API_URL przy ewentualnym deployu, lokalnie fallback
const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export async function fetchFlights() {
  const res = await fetch(`${API_BASE}/flights`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchTrack(icao24) {
  const res = await fetch(`${API_BASE}/track/${icao24}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchFlightInfo(icao24, callsign) {
  const res = await fetch(`${API_BASE}/flightinfo/${icao24}/${callsign}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
