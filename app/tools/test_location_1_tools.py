from __future__ import annotations
import json
from app.tools import location_tools


def test_location_is_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("KUMA_LOCATION_CONFIG_DIR", str(tmp_path))
    assert location_tools.live_location_enabled() is False


def test_location_opt_in_never_enables_history(monkeypatch, tmp_path):
    monkeypatch.setenv("KUMA_LOCATION_CONFIG_DIR", str(tmp_path))
    location_tools.set_live_location_enabled(True)
    payload = json.loads((tmp_path / "preferences.json").read_text())
    assert payload["enabled"] is True
    assert payload["history_enabled"] is False


def test_public_location_evidence_rounds_coordinates(monkeypatch, tmp_path):
    monkeypatch.setenv("KUMA_LOCATION_CONFIG_DIR", str(tmp_path))
    location_tools.set_live_location_enabled(True)
    monkeypatch.setattr(location_tools, "_CACHE_VALUE", None)
    monkeypatch.setattr(location_tools, "_CACHE_TIME", 0.0)
    monkeypatch.setattr(
        location_tools,
        "_run_native_helper",
        lambda: {
            "ok": True,
            "latitude": 12.9715987,
            "longitude": 77.594566,
            "horizontal_accuracy_m": 18.0,
            "timestamp": "2026-09-10T17:00:00Z",
            "authorization": "authorized_when_in_use",
            "locality": "Bengaluru",
            "administrative_area": "Karnataka",
            "country": "India",
            "iso_country_code": "IN",
        },
    )
    result = location_tools.get_current_location()
    assert result.success is True
    text = str(result.result)
    assert "WEATHER_LOCATION: Bengaluru, Karnataka, India" in text
    assert "LATITUDE_APPROX: 12.97" in text
    assert "LONGITUDE_APPROX: 77.59" in text
    assert "12.9715987" not in text
    assert "77.594566" not in text
    assert "LOCATION_HISTORY_PERSISTED: false" in text
    assert "AUTHORITY: NONE" in text


def test_disabled_location_does_not_invoke_helper(monkeypatch, tmp_path):
    monkeypatch.setenv("KUMA_LOCATION_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        location_tools,
        "_run_native_helper",
        lambda: (_ for _ in ()).throw(AssertionError("helper called")),
    )
    result = location_tools.get_current_location()
    assert result.success is False
