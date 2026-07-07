//panel szczegolow wybranego lotu
import { useEffect, useState } from 'react'
import { fetchFlightInfo } from '../api.js'

//kody awaryjne squawks transpondera - kazdy pilot zna te trzy
const SPECIAL_SQUAWKS = {
  7500: 'HIJACK',
  7600: 'RADIO FAIL',
  7700: 'EMERGENCY',
}

export default function DetailsPanel({ flight, onClose }) {
  //wzbogacenie z adsbdb - linia, trasa, typ maszyny, poki sie laduje to null
  const [info, setInfo] = useState(null)

  useEffect(() => {
    setInfo(null)
    if (!flight.callsign) return
    let alive = true
    fetchFlightInfo(flight.icao24, flight.callsign)
      .then((d) => {
        if (alive) setInfo(d)
      })
      .catch(() => {}) //wzbogacenie jest opcjonalne - panel dziala i bez niego
    return () => {
      alive = false
    }
  }, [flight.icao24, flight.callsign])

  const vr = flight.vertical_rate
  //strzalka trendu pionowego, blisko zera - lot poziomy
  const trend = vr == null || Math.abs(vr) < 0.5 ? '→' : vr > 0 ? '↑' : '↓'
  const age = flight.last_contact
    ? Math.max(0, Math.round(Date.now() / 1000 - flight.last_contact))
    : null
  const special = SPECIAL_SQUAWKS[flight.squawk]

  const airline = info?.route?.airline
  const origin = info?.route?.origin
  const dest = info?.route?.destination
  const aircraft = info?.aircraft
  //monogram linii - kod ICAO z bazy albo 3 pierwsze znaki callsignu
  const mono = airline?.icao || (flight.callsign || '???').slice(0, 3)

  const rows = [
    ['SQK', `${flight.squawk || '----'}${special ? ` · ${special}` : ''}`, special ? 'alert' : ''],
    ['ALT', flight.altitude != null ? `${Math.round(flight.altitude)} m` : '—'],
    ['GS', flight.velocity != null ? `${Math.round(flight.velocity * 3.6)} km/h` : '—'],
    ['TRK', flight.track != null ? `${Math.round(flight.track)}°` : '—'],
    ['V/S', vr != null ? `${trend} ${Math.abs(vr).toFixed(1)} m/s` : '—'],
    ...(aircraft?.type ? [['TYPE', aircraft.type]] : []),
    ...(aircraft?.registration ? [['REG', aircraft.registration]] : []),
    ['ICAO24', flight.icao24.toUpperCase()],
    ['SEEN', age != null ? `${age} s ago` : '—'],
  ]

  return (
    <aside className="panel">
      <div className="panel-head">
        <div className="panel-ident">
          <span className="panel-mono">{mono}</span>
          <div>
            <span className="panel-callsign">{flight.callsign || flight.icao24.toUpperCase()}</span>
            {airline?.name && <span className="panel-airline">{airline.name}</span>}
          </div>
        </div>
        <button className="panel-close" onClick={onClose}>
          ×
        </button>
      </div>

      {/*trasa skad-dokad, gdy baza ja zna*/}
      {origin?.iata && dest?.iata && (
        <div className="panel-route">
          <div className="route-codes">
            <b>{origin.iata}</b>
            <span className="route-arrow">→</span>
            <b>{dest.iata}</b>
          </div>
          <div className="route-cities">
            <span>{origin.city}</span>
            <span>{dest.city}</span>
          </div>
        </div>
      )}

      <dl className="panel-rows">
        {rows.map(([label, value, cls]) => (
          <div className="panel-row" key={label}>
            <dt>{label}</dt>
            <dd className={cls || ''}>{value}</dd>
          </div>
        ))}
      </dl>
    </aside>
  )
}
