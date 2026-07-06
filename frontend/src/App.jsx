//glowny komponent - sklada mape, gorny pasek statusu i stopke z danymi
import { useEffect, useRef, useState } from 'react'
import RadarMap from './components/RadarMap.jsx'
import DetailsPanel from './components/DetailsPanel.jsx'
import { fetchFlights, fetchTrack } from './api.js'
import './App.css'

const REFRESH_MS = 10000 //co ile pytam backend o swieze pozycje

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

  useEffect(() => {
    let alive = true

    async function load() {
      try {
        const data = await fetchFlights()
        if (!alive) return

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
    fetchTrack(selectedId)
      .then((d) => {
        if (alive && d.path.length > 1) setTrackPath(d.path)
      })
      .catch(() => {}) //brak trasy z API - zostaje przy wlasnej historii
    return () => {
      alive = false
    }
  }, [selectedId])

  const airborne = flights.filter((f) => !f.on_ground).length
  const badge = BADGES[status]
  const showChip = status === 'loading' || (status === 'error' && flights.length === 0)
  const shown = hideGround ? flights.filter((f) => !f.on_ground) : flights
  const selected = shown.find((f) => f.icao24 === selectedId) ?? null
  //sciezka z API ma pierwszenstwo, fallback - wlasna historia z odswiezen
  const trail = trackPath ?? (selected ? [...(trailsRef.current.get(selected.icao24)?.pts ?? [])] : [])

  //sciezka z API to stan na moment kliku - kolejne odswiezenia dopisuja biezaca pozycje
  useEffect(() => {
    if (!trackPath || !selected) return
    const last = trackPath[trackPath.length - 1]
    if (last[0] !== selected.lat || last[1] !== selected.lon) {
      setTrackPath([...trackPath, [selected.lat, selected.lon]])
    }
  }, [trackPath, selected])

  return (
    <div className="app">
      <RadarMap flights={shown} selectedId={selectedId} onSelect={setSelectedId} trail={trail} />
      {lastUpdate && <div className="ping" key={lastUpdate.getTime()} />}
      <div className="vignette" />

      <header className="topbar">
        <div className="brand">
          <img src="/favicon.svg" width="30" height="30" alt="" />
          <div>
            <span className="brand-name">SQUAWK</span>
            <span className="brand-sub">ads-b live · sector PL</span>
          </div>
        </div>

        <div className="stats">
          <button className={`toggle ${hideGround ? 'on' : ''}`} onClick={() => setHideGround((v) => !v)}>
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

      {selected && <DetailsPanel flight={selected} onClose={() => setSelectedId(null)} />}

      <footer className="databar">DATA · OpenSky Network · refresh {REFRESH_MS / 1000}s</footer>
    </div>
  )
}
