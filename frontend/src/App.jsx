//glowny komponent - sklada mape, gorny pasek statusu i stopke z danymi
import { useEffect, useRef, useState } from 'react'
import RadarMap from './components/RadarMap.jsx'
import DetailsPanel from './components/DetailsPanel.jsx'
import AirportBoard from './components/AirportBoard.jsx'
import { fetchFlights, fetchTrack, fetchBoard } from './api.js'
import './App.css'

const REFRESH_MS = 10000 //co ile pytam backend o swieze pozycje
const HOME = { lat: 52.1, lon: 19.4 } //sektor domowy - srodek polski

//etykieta sektora
function sectorLabelFor(lat, lon) {
  return `${Math.abs(lat).toFixed(1)}${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(1)}${lon >= 0 ? 'E' : 'W'}`
}


//teksty i style plakietki statusu
const BADGES = {
  loading: { label: 'INIT', cls: 'loading' },
  live: { label: 'LIVE', cls: 'live' },
  stale: { label: 'STALE', cls: 'stale' },
  error: { label: 'NO LINK', cls: 'error' },
}

export default function App() {
  const [flights, setFlights] = useState([])
  const [status, setStatus] = useState('loading')
  const [lastUpdate, setLastUpdate] = useState(null)
  const [selectedId, setSelectedId] = useState(null) //icao24 kliknietego samolotu
  const [hideGround, setHideGround] = useState(false) //filtr - ukryj maszyny na ziemi
  const trailsRef = useRef(new Map())
  //pelna sciezka wybranego lotu od startu (z API), null - wlasna historia
  const [trackPath, setTrackPath] = useState(null)
  //zakres sladu: leg - biezacy odcinek, day - wszystkie dzisiejsze przeloty maszyny
  const [trackScope, setTrackScope] = useState('leg')
  //sektor: ref zamiast stanu, zeby zmiana nie restartowala petli odpytywania
  //sektor pobierania - zmienia sie wylacznie swiadoma akcja (set sector / home / tablica)
  const [sector, setSector] = useState(HOME)
  const sectorRef = useRef(HOME)
  const loadRef = useRef(null) //aktualna funkcja load, wolana przy zmianie sektora
  const firstSector = useRef(true) //pierwsze ustawienie nie ma czyscic mapy
  //tryb wyboru: okrag wyboru podaza za srodkiem widoku az do zatwierdzenia
  const [pickMode, setPickMode] = useState(false)
  const [ghost, setGhost] = useState(HOME)
  const viewCenterRef = useRef(HOME) //ostatni srodek widoku mapy
  //cel dolotu kamery - klik w tablicy albo przycisk home
  const [focus, setFocus] = useState(null)
  //tablica lotniska
  const [boardOpen, setBoardOpen] = useState(false)
  const [boardAirport, setBoardAirport] = useState('WAW')
  const [board, setBoard] = useState(null) //dane tablicy, null - laduje sie

  useEffect(() => {
    let alive = true

    async function load() {
      try {
        const s = sectorRef.current
        const data = await fetchFlights(s.lat, s.lon)
        if (!alive || sectorRef.current !== s) return

        const trails = trailsRef.current
        const seen = new Set()
        data.flights.forEach((f) => {
          seen.add(f.icao24)
          const entry = trails.get(f.icao24) ?? { pts: [], miss: 0 }
          entry.miss = 0
          const last = entry.pts[entry.pts.length - 1]
          if (!last || last[0] !== f.lat || last[1] !== f.lon) {
            entry.pts.push([f.lat, f.lon])
            if (entry.pts.length > 40) entry.pts.shift() //ok. 6 minut historii przy odswiezaniu co 10s
          }
          trails.set(f.icao24, entry)
        })
        for (const [key, entry] of trails) {
          if (!seen.has(key) && ++entry.miss >= 6) trails.delete(key)
        }

        setFlights(data.flights)
        setStatus(data.stale ? 'stale' : 'live')
        setLastUpdate(new Date())
      } catch {
        if (alive) setStatus('error')
      }
    }

    function poll() {
      if (document.hidden) return
      load()
    }

    function onVisible() {
      if (!document.hidden) load() //powrot na karte - od razu swieze dane zamiast czekania na tick
    }

    loadRef.current = load //zmiana sektora wywoluje swieze pobranie natychmiast
    load() //pierwsze pobranie zawsze, nawet gdy karta w tle
    const id = setInterval(poll, REFRESH_MS)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      alive = false
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  //zywy tytul karty - liczbe celow widac z innej karty przegladarki
  useEffect(() => {
    document.title = `Squawk · ${flights.length} tracked`
  }, [flights.length])

  //po wyborze samolotu dociagam pelna trase od startu lotu
  useEffect(() => {
    setTrackPath(null)
    if (!selectedId) return
    let alive = true
    fetchTrack(selectedId, trackScope)
      .then((d) => {
        //sciezka z wlascicielem
        if (alive && d.path.length > 1) setTrackPath({ icao24: selectedId, path: d.path })
      })
      .catch(() => {}) //brak trasy z API - zostaje przy wlasnej historii
    return () => {
      alive = false
    }
  }, [selectedId, trackScope])

  //tablica - pobranie po otwarciu/zmianie lotniska + odswiezanie co 30s poki otwarta
  useEffect(() => {
    if (!boardOpen) return
    let alive = true
    setBoard(null)
    const load = () =>
      fetchBoard(boardAirport)
        .then((d) => alive && setBoard(d))
        .catch(() => alive && setBoard({ error: true }))
    load()
    const id = setInterval(load, 30000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [boardOpen, boardAirport])

  //zmiana sektora - czyszcze stare cele i od razu pobieram nowe - 1-3s zamiast 10s
  useEffect(() => {
    sectorRef.current = sector
    if (firstSector.current) {
      firstSector.current = false
      return
    }
    setFlights([])
    setStatus('loading')
    loadRef.current?.()
  }, [sector])

  //esc wychodzi z trybu wyboru sektora
  useEffect(() => {
    if (!pickMode) return
    const onKey = (e) => e.key === 'Escape' && setPickMode(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [pickMode])

  //ruch mapy nie zmienia sektora - tylko aktualizuje srodek widoku i okregu wyboru
  function handleMoveEnd(lat, lon) {
    viewCenterRef.current = { lat, lon }
    if (pickMode) setGhost({ lat, lon })
  }

  function startPick() {
    setGhost(viewCenterRef.current)
    setPickMode(true)
  }

  function confirmSector() {
    setPickMode(false)
    setSector({ ...ghost })
  }

  function goHome() {
    setPickMode(false)
    setSector(HOME)
    setFocus({ ...HOME, zoom: 6, exact: true, ts: Date.now() })
  }

  //klik w wiersz tablicy - zaznacz i dolec kamera - gdy sektor za granica - swiadomy powrot do domu
  function pickFromBoard(icao24) {
    setSelectedId(icao24)
    const f = flights.find((x) => x.icao24 === icao24)
    if (f) {
      setFocus({ lat: f.lat, lon: f.lon, zoom: 7, exact: false, ts: Date.now() })
    } else {
      setSector(HOME)
      setFocus({ ...HOME, zoom: 6, exact: true, ts: Date.now() })
    }
  }

  const airborne = flights.filter((f) => !f.on_ground).length
  const badge = BADGES[status]
  const showChip = status === 'loading' || (status === 'error' && flights.length === 0)
  const shown = hideGround ? flights.filter((f) => !f.on_ground) : flights
  const selected = shown.find((f) => f.icao24 === selectedId) ?? null
  //sciezka z API liczy sie tylko gdy nalezy do wybranego, inaczej wlasna historia z odswiezen
  const apiTrail = trackPath && selected && trackPath.icao24 === selected.icao24 ? trackPath.path : null
  const trail = apiTrail ?? (selected ? [...(trailsRef.current.get(selected.icao24)?.pts ?? [])] : [])

  //sciezka z API to stan na moment kliku - kolejne odswiezenia dopisuja biezaca pozycje
  useEffect(() => {
    if (!trackPath || !selected || trackPath.icao24 !== selected.icao24) return
    const pts = trackPath.path
    const last = pts[pts.length - 1]
    if (last[0] !== selected.lat || last[1] !== selected.lon) {
      setTrackPath({ icao24: trackPath.icao24, path: [...pts, [selected.lat, selected.lon]] })
    }
  }, [trackPath, selected])

  return (
    <div className="app">
      <RadarMap
        flights={shown}
        selectedId={selectedId}
        onSelect={setSelectedId}
        trail={trail}
        onMoveEnd={handleMoveEnd}
        focus={focus}
        sector={sector}
        ghost={ghost}
        pickMode={pickMode}
      />
      {lastUpdate && <div className="ping" key={lastUpdate.getTime()} />}
      <div className="vignette" />

      <header className="topbar">
        <div className="brand">
          <img src="/favicon.svg" width="30" height="30" alt="" />
          <div>
            <span className="brand-name">SQUAWK</span>
            <span className="brand-sub">
              ads-b live · sector {sectorLabelFor(pickMode ? ghost.lat : sector.lat, pickMode ? ghost.lon : sector.lon)}
            </span>
          </div>
          {/*sterowanie sektorem - nawigacja po lewej, stan i widoki po prawej*/}
          <button className={`toggle ${pickMode ? 'on' : ''}`} onClick={() => (pickMode ? setPickMode(false) : startPick())}>
            SECTOR
          </button>
          <button className="toggle" onClick={goHome}>
            HOME
          </button>
        </div>

        <div className="stats">
          <button className={`toggle ${boardOpen ? 'on' : ''}`} onClick={() => setBoardOpen((v) => !v)}>
            BOARD
          </button>
          {/*swieci sie gdy cele naziemne sa pokazywane*/}
          <button className={`toggle ${hideGround ? '' : 'on'}`} onClick={() => setHideGround((v) => !v)}>
            {hideGround ? 'GND OFF' : 'GND ON'}
          </button>
          <span className={`badge ${badge.cls}`}>
            <span className="dot" />
            {badge.label}
          </span>
          <span className="stat">
            <b>{airborne}</b> airborne
          </span>
          <span className="stat">
            <b>{flights.length}</b> tracked
          </span>
          {lastUpdate && (
            <span className="stat time">
              {/*czas UTC*/}
              {lastUpdate.toLocaleTimeString('en-GB', { timeZone: 'UTC', hour12: false })} UTC
            </span>
          )}
        </div>
      </header>

      {showChip && (
        <div className={`init-chip ${status === 'error' ? 'error' : ''}`}>
          {status === 'error' ? 'no data link — retrying' : 'acquiring ads-b signal'}
        </div>
      )}

      {boardOpen && (
        <AirportBoard
          board={board}
          airport={boardAirport}
          onAirport={setBoardAirport}
          onPick={pickFromBoard}
          selectedId={selectedId}
          onClose={() => setBoardOpen(false)}
        />
      )}

      {selected && (
        <DetailsPanel
          flight={selected}
          scope={trackScope}
          onScope={setTrackScope}
          onClose={() => setSelectedId(null)}
        />
      )}

      {pickMode && (
        <div className="pick-bar">
          <span>
            AIM WITH MAP · <b>{sectorLabelFor(ghost.lat, ghost.lon)}</b>
          </span>
          <button onClick={confirmSector}>SET SECTOR</button>
          <button onClick={() => setPickMode(false)}>
            CANCEL
          </button>
        </div>
      )}

      <footer className="databar">DATA · adsb.fi · refresh {REFRESH_MS / 1000}s</footer>
    </div>
  )
}
