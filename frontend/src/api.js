//komunikacja z backendem FastAPI
const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export async function fetchFlights(lat, lon) {
  const res = await fetch(`${API_BASE}/flights?lat=${lat.toFixed(3)}&lon=${lon.toFixed(3)}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchTrack(icao24, scope = 'leg') {
  const res = await fetch(`${API_BASE}/track/${encodeURIComponent(icao24)}?scope=${scope}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchBoard(airport) {
  const res = await fetch(`${API_BASE}/board/${encodeURIComponent(airport)}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchFlightInfo(icao24, callsign) {
  const res = await fetch(`${API_BASE}/flightinfo/${encodeURIComponent(icao24)}/${encodeURIComponent(callsign)}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
