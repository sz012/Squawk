//pojedynczy samolot na mapie
import { useMemo } from 'react'
import L from 'leaflet'
import { Marker, Tooltip } from 'react-leaflet'

//autorska sylwetka airlinera
const PLANE_PATH =
  'M16 2c.9 0 1.5 1.2 1.5 2.6v6.8l10.6 6.1c.5.3.9.9.9 1.5v1.6l-11.5-3.4v6.6l3 2.2v2l-4.5-1.3-4.5 1.3v-2l3-2.2v-6.6L3 20.6V19c0-.6.4-1.2.9-1.5l10.6-6.1V4.6C14.5 3.2 15.1 2 16 2z'

function planeIcon(rot, vector, onGround) {
  const color = onGround ? '#4f5d72' : '#f2eadb' //cieple "echo" radarowe, na ziemi przygaszone
  const glow = onGround ? 'none' : 'drop-shadow(0 0 5px rgba(255,196,120,.45))'
  //wektor predkosci jak na skopie ATC - kreska przed nosem, dlugosc rosnie z predkoscia
  const vectorLine = vector
    ? `<line x1="16" y1="2.5" x2="16" y2="${2.5 - vector}" stroke="${color}" stroke-width="1.5" stroke-linecap="round" opacity=".5"/>`
    : ''

  return L.divIcon({
    className: 'plane-icon',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    html: `<svg viewBox="0 0 32 32" width="30" height="30" style="overflow:visible;transform:rotate(${rot}deg);filter:${glow}">${vectorLine}<path d="${PLANE_PATH}" fill="${color}"/></svg>`,
  })
}

export default function PlaneMarker({ flight }) {
  //zaokraglam kurs i wektor przed useMemo - ikonka podmienia sie tylko przy realnej zmianie, nie przy kazdym szumie pomiaru
  const rot = Math.round((flight.track ?? 0) / 5) * 5
  const speed = flight.velocity ?? 0
  const vector = flight.on_ground || speed < 40 ? 0 : Math.round(Math.min(13, speed * 0.045))

  const icon = useMemo(
    () => planeIcon(rot, vector, flight.on_ground),
    [rot, vector, flight.on_ground],
  )

  const alt = flight.altitude != null ? `${Math.round(flight.altitude)} m` : '—'
  const spd = flight.velocity != null ? `${Math.round(flight.velocity * 3.6)} km/h` : '—' //m/s -> km/h

  return (
    <Marker position={[flight.lat, flight.lon]} icon={icon} riseOnHover>
      <Tooltip direction="top" offset={[0, -14]} className="sqk-tip">
        <b>{flight.callsign || flight.icao24.toUpperCase()}</b>
        <span>ALT {alt} · SPD {spd}</span>
      </Tooltip>
    </Marker>
  )
}
