"""Sağlayıcı durumu ipucu satırları: Ollama /api/ps ve DeepL kotası (sahte HTTP, gerçek ağ yok)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from nxceviri.core.translate.probe import ollama_summary, parse_expiry

NOW = datetime(2026, 11, 9, 12, 0, 0, tzinfo=UTC)


def _client(payload: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=payload)))


def test_parse_expiry_truncates_nanoseconds_and_keeps_zone() -> None:
    parsed = parse_expiry("2026-11-09T15:04:05.123456789+03:00")
    assert parsed == datetime(2026, 11, 9, 12, 4, 5, 123456, tzinfo=UTC)
    assert parse_expiry("saçma") is None


def test_forever_cpu_only_and_expiring() -> None:
    far = {"name": "m", "size": 10, "size_vram": 0, "expires_at": "2318-01-01T00:00:00Z"}
    lines = ollama_summary("http://x", "m", _client({"models": [far]}), lambda: NOW)
    assert lines == ["Model: m", "Bellekte: CPU", "Kalan süre: süresiz"]
    soon = {"name": "m", "size": 10, "size_vram": 10, "expires_at": "2026-11-09T12:00:30Z"}
    lines = ollama_summary("http://x", "m", _client({"models": [soon]}), lambda: NOW)
    assert lines[1:] == ["Bellekte: GPU %100", "Kalan süre: 30 sn"]


def test_no_model_selected_and_bad_json() -> None:
    assert ollama_summary("http://x", "", _client({"models": []}), lambda: NOW)[0] == "Model seçilmedi"
    assert ollama_summary("http://x", "m", _client(["beklenmeyen"]), lambda: NOW) == ["Ollama'ya bağlanılamadı."]
