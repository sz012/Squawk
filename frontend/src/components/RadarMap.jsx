//mapa
import { MapContainer, TileLayer, Pane, ZoomControl } from 'react-leaflet'
import PlaneMarker from './PlaneMarker.jsx'

//ciemne kafelki CARTO - puste tlo + etykiety nazw
const TILE_BASE = 'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png'
const TILE_LABELS = 'https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png'
const TILE_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'

const CENTER = [52.1, 19.4] //srodek Polski

export default function RadarMap({ flights }) {
  return (
    <MapContainer center={CENTER} zoom={6} minZoom={4} zoomControl={false} className="map">
      <TileLayer url={TILE_BASE} attribution={TILE_ATTR} subdomains="abcd" maxZoom={19} />
      <Pane name="labels" style={{ zIndex: 350, opacity: 0.55, pointerEvents: 'none' }}>
        <TileLayer url={TILE_LABELS} subdomains="abcd" maxZoom={19} />
      </Pane>
      <ZoomControl position="bottomright" />
      {flights.map((f) => (
        <PlaneMarker key={f.icao24} flight={f} />
      ))}
    </MapContainer>
  )
}
