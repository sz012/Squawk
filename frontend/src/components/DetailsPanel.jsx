//panel szczegolow wybranego lotu

//kody awaryjne transpondera - kazdy pilot zna te trzy
const SPECIAL_SQUAWKS = {
  7500: 'HIJACK',
  7600: 'RADIO FAIL',
  7700: 'EMERGENCY',
}

export default function DetailsPanel({ flight, onClose }) {
  const vr = flight.vertical_rate
  //strzalka trendu pionowego; blisko zera = lot poziomy
  const trend = vr == null || Math.abs(vr) < 0.5 ? '→' : vr > 0 ? '↑' : '↓'
  //wiek danych - ile sekund temu samolot ostatnio sie odezwal
  const age = flight.last_contact
    ? Math.max(0, Math.round(Date.now() / 1000 - flight.last_contact))
    : null
  const special = SPECIAL_SQUAWKS[flight.squawk]

  const rows = [
    ['COUNTRY', flight.country ?? '—'],
    ['ALT', flight.altitude != null ? `${Math.round(flight.altitude)} m` : '—'],
    ['GS', flight.velocity != null ? `${Math.round(flight.velocity * 3.6)} km/h` : '—'],
    ['TRK', flight.track != null ? `${Math.round(flight.track)}°` : '—'],
    ['V/S', vr != null ? `${trend} ${Math.abs(vr).toFixed(1)} m/s` : '—'],
    ['ICAO24', flight.icao24.toUpperCase()],
    ['SEEN', age != null ? `${age} s ago` : '—'],
  ]

  return (
    <aside className="panel">
      <div className="panel-head">
        <div>
          <span className="panel-callsign">{flight.callsign || flight.icao24.toUpperCase()}</span>
          <span className={`panel-squawk ${special ? 'alert' : ''}`}>
            SQK {flight.squawk || '----'}
            {special ? ` · ${special}` : ''}
          </span>
        </div>
        <button className="panel-close" onClick={onClose}>
          ×
        </button>
      </div>
      <dl className="panel-rows">
        {rows.map(([label, value]) => (
          <div className="panel-row" key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </aside>
  )
}
