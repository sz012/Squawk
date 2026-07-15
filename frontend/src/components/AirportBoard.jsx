//tablica lotniska - przyloty i odloty wyliczane z zywego ruchu i tras adsbdb

const AIRPORTS = ['WAW', 'KRK', 'GDN', 'KTW']

export default function AirportBoard({ board, airport, onAirport, onPick, selectedId, onClose }) {
  return (
    <aside className="board">
      <div className="board-head">
        <span className="board-title">AIRPORT BOARD</span>
        <button className="panel-close" onClick={onClose}>
          ×
        </button>
      </div>

      <div className="board-pills">
        {AIRPORTS.map((code) => (
          <button key={code} className={code === airport ? 'on' : ''} onClick={() => onAirport(code)}>
            {code}
          </button>
        ))}
      </div>

      {!board && <div className="board-empty">querying routes…</div>}
      {board?.error && <div className="board-empty">board unavailable</div>}

      {board && !board.error && (
        <>
          <div className="board-section">ARRIVALS</div>
          {board.arrivals.length === 0 && <div className="board-empty">no inbound traffic</div>}
          {board.arrivals.map((r) => (
            //klik w wiersz zaznacza samolot na mapie
            <button
              key={r.icao24}
              className={`board-row ${r.icao24 === selectedId ? 'sel' : ''}`}
              onClick={() => onPick(r.icao24)}
            >
              <span className="br-cs">{r.callsign}</span>
              <span className="br-mid">
                {r.from.iata || '—'}
                <i>{r.from.city || ''}</i>
              </span>
              <span className="br-eta">{r.landed ? 'LANDED' : r.eta_min != null ? `${r.eta_min}'` : '—'}</span>
            </button>
          ))}

          <div className="board-section">DEPARTURES</div>
          {board.departures.length === 0 && <div className="board-empty">no outbound traffic</div>}
          {board.departures.map((r) => (
            <button
              key={r.icao24}
              className={`board-row ${r.icao24 === selectedId ? 'sel' : ''}`}
              onClick={() => onPick(r.icao24)}
            >
              <span className="br-cs">{r.callsign}</span>
              <span className="br-mid">
                {r.to.iata || '—'}
                <i>{r.to.city || ''}</i>
              </span>
              <span className={`br-eta ${r.status === 'OUT' ? 'out' : ''}`}>{r.status}</span>
            </button>
          ))}
        </>
      )}
    </aside>
  )
}
