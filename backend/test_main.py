#/backend pytest
import time
import main

#jednostki lotnicze -> jednostki metryczne
def test_parse_aircraft_przelicza_jednostki():
    ac = {"hex": "4d248e", "flight": "  WZZ18DM ", "alt_baro": 35000, "gs": 400, "track": 264.7, "baro_rate": -640, "squawk": "1000", "seen": 2, "lat": 52.0, "lon": 19.0}
    f = main._parse_aircraft(ac)
    assert f["altitude"] == 10668.0
    assert f["velocity"] == 205.8
    assert f["vertical_rate"] == -3.3
    assert f["callsign"] == "WZZ18DM"
    assert f["on_ground"] is False

#na ziemi zamiast liczby jest "ground"
def test_parse_aircraft_na_ziemi():
    f = main._parse_aircraft({"hex": "abc123", "alt_baro": "ground", "lat": 50.0, "lon": 19.8, "seen": 0})
    assert f["on_ground"] is True
    assert f["altitude"] is None
    assert f["callsign"] is None

def test_parse_aircraft_wiek_sygnalu():
    f = main._parse_aircraft({"hex": "abc123", "alt_baro": 1000, "lat": 50.0, "lon": 19.8, "seen": 30})
    assert abs((time.time() - 30) - f["last_contact"]) < 2

#wycinanie biezacego odcinka z historii calego dnia
#punkt trace - [offset_s, lat, lon, wysokosc("ground" - na ziemi), predkosc]
def _rejs(t0, t1, alt=10000, krok=100):
    return [[t, 50.0, 19.0, alt, 400] for t in range(t0, t1 + 1, krok)]

def _postoj(t0, t1, krok=400):
    return [[t, 50.1, 19.1, "ground", 5] for t in range(t0, t1 + 1, krok)]

def test_current_leg_tnie_na_postoju():
    trace = _rejs(0, 1000) + _postoj(1100, 4900) + [[4950, 50.1, 19.1, "ground", 30]] + _rejs(5000, 6000)
    leg = main._current_leg(trace)
    assert leg[0][0] == 4950

def test_current_leg_tnie_na_przerwie_w_danych():
    trace = _rejs(0, 1000) + _rejs(3000, 4000)
    leg = main._current_leg(trace)
    assert leg[0][0] == 3000

def test_current_leg_jeden_ciagly_rejs_bez_ciec():
    trace = _rejs(0, 2000)
    assert main._current_leg(trace) == trace

def test_current_leg_pusta_lista():
    assert main._current_leg([]) == []

#klucz sektora - zaokraglanie do siatki 0.1 stopnia
def test_sector_key_zaokragla():
    assert main._sector_key(52.149, 19.351) == "52.1,19.4"
    assert main._sector_key(-33.87, 151.21) == "-33.9,151.2"

#geometria, odleglosc i namiar
def test_haversine_stopien_szerokosci():
    d = main._haversine_km(0.0, 0.0, 1.0, 0.0)
    assert 110.5 < d < 112.0

def test_bearing_kierunki_glowne():
    assert abs(main._bearing_deg(0.0, 0.0, 1.0, 0.0) - 0.0) < 0.01  #na polnoc
    assert abs(main._bearing_deg(0.0, 0.0, 0.0, 1.0) - 90.0) < 0.01  #na wschod
