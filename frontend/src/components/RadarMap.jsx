//mapa
import { useEffect } from 'react'
import { Circle, MapContainer, TileLayer, Pane, ZoomControl, Polyline, useMap, useMapEvents } from 'react-leaflet'
import PlaneMarker from './PlaneMarker.jsx'

//ciemne kafelki CARTO - puste tlo + etykiety nazw
const TILE_BASE = 'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png'
const TILE_LABELS = 'https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png'
const TILE_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'

const CENTER = [52.1, 19.4] //srodek Polski
const SECTOR_RADIUS_M = 250 * 1852 //250 mil morskich - zasieg jednego zapytania do adsb.lol

//klik w pusta mape odznacza wybrany samolot
function DeselectOnClick({ onSelect }) {
  useMapEvents({ click: () => onSelect(null) })
  return null
}

//po kazdym przesunieciu/zoomie zglasza nowy srodek widoku - radar podaza za mapa
function SectorWatcher({ onMove }) {
  const map = useMapEvents({
    moveend: () => {
      const c = map.getCenter()
      onMove(c.lat, c.lng)
    },
  })
  return null
}

//dolec kamera do wskazanego punktu (klikniecie w tablicy, przycisk home)
function MapController({ focus }) {
  const map = useMap()
  useEffect(() => {
    if (!focus) return
    const zoom = focus.exact ? focus.zoom : Math.max(map.getZoom(), focus.zoom)
    map.flyTo([focus.lat, focus.lon], zoom, { duration: 1.2 })
  }, [focus, map])
  return null
}

let zoomTimer

//na czas animacji zoomu zdejmuje najdrozsze efekty (filtry, blury, tranzycje)
function ZoomPerfGuard() {
  useMapEvents({
    zoomstart: () => {
      clearTimeout(zoomTimer)
      document.body.classList.add('zooming')
    },
    zoomend: () => {
      clearTimeout(zoomTimer)
      zoomTimer = setTimeout(() => document.body.classList.remove('zooming'), 150)
    },
  })
  return null
}

export default function RadarMap({ flights, selectedId, onSelect, trail, onMoveEnd, focus, sector, ghost, pickMode }) {
  return (
    <MapContainer center={CENTER} zoom={6} minZoom={4} zoomControl={false} className="map">
      <TileLayer url={TILE_BASE} attribution={TILE_ATTR} subdomains="abcd" maxZoom={19} />
      <Pane name="labels" style={{ zIndex: 350, opacity: 0.55, pointerEvents: 'none' }}>
        <TileLayer url={TILE_LABELS} subdomains="abcd" maxZoom={19} />
      </Pane>
      <ZoomControl position="bottomright" />
      <DeselectOnClick onSelect={onSelect} />
      <ZoomPerfGuard />
      <SectorWatcher onMove={onMoveEnd} />
      <MapController focus={focus} />
      {/*granica obszaru pobierania danych, w trybie wyboru dodatkowo jasniejszy okrag wyboru*/}
      <Circle
        center={[sector.lat, sector.lon]}
        radius={SECTOR_RADIUS_M}
        pathOptions={{
          color: '#ffb454',
          weight: 1,
          opacity: pickMode ? 0.15 : 0.35,
          fillColor: '#ffb454',
          fillOpacity: pickMode ? 0.01 : 0.03,
          dashArray: '6 8',
        }}
        interactive={false}
      />
      {pickMode && (
        <Circle
          center={[ghost.lat, ghost.lon]}
          radius={SECTOR_RADIUS_M}
          pathOptions={{ color: '#ffb454', weight: 2, opacity: 0.8, fillColor: '#ffb454', fillOpacity: 0.05, dashArray: '4 6' }}
          interactive={false}
        />
      )}
      {/*slad trasy wybranego samolotu - pelny odcinek z api albo wlasna historia*/}
      {trail.length > 1 && (
        <Polyline positions={trail} pathOptions={{ color: '#ffb454', weight: 2, opacity: 0.45 }} interactive={false} />
      )}
      {flights.map((f) => (
        <PlaneMarker
          key={f.icao24}
          flight={f}
          selected={f.icao24 === selectedId}
          onSelect={onSelect}
        />
      ))}
    </MapContainer>
  )
}
