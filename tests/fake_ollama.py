"""Testler için sahte Ollama sunucusu (httpx.MockTransport üzerinden, ağ kullanmaz).

Gerçek Ollama API'sinin yanıt biçimlerini taklit eder: /api/version, /api/tags,
/api/show, /api/chat (format alanlı; akış isteğinde NDJSON parçalar). Redaksiyon isteklerinde (maddelerde "current"
alanı varsa) `revise` ile yanıt verir.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from nxceviri.core.translate.providers.ollama import OllamaProvider


def fake_translate(text: str) -> str:
    """Yer tutucuları koruyarak "çeviri" üretir: her sözcüğün başına "tr-" ekler."""
    return re.sub(r"(?<![⟦\w])([A-Za-z]+)", r"tr-\1", text)


def fake_revise(item: dict[str, Any]) -> str:
    """Redaksiyon maddesi için "düzeltilmiş" çeviri: özgün metinden "dz-" önekli sahte çeviri."""
    return fake_translate(item["text"]).replace("tr-", "dz-")


def fake_suggest(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Sözlük önerisi isteğine her aday için sahte karşılık."""
    terms: list[dict[str, Any]] = payload["terms"]
    return [{"term": t["term"], "translation": f"tr-{t['term']}", "note": "öneri notu", "add": True} for t in terms]


@dataclass
class FakeOllama:
    models: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "name": "gemma4:12b",
                "size": 8_000_000_000,
                "details": {"parameter_size": "12B", "quantization_level": "Q4_K_M"},
            },
            {"name": "bge-m3:latest", "size": 1_200_000_000, "details": {"parameter_size": "567M"}},
        ]
    )
    capabilities: dict[str, list[str]] = field(
        default_factory=lambda: {"gemma4:12b": ["completion", "thinking"], "bge-m3:latest": ["embedding"]}
    )
    translate: Callable[[str], str] = fake_translate
    #: Redaksiyon maddeleri ("current" alanı olan) için dönen metin.
    revise: Callable[[dict[str, Any]], str] = fake_revise
    #: Sözlük önerisi isteğine (yanıt şemasında "terms") dönen maddeler.
    suggest: Callable[[dict[str, Any]], list[dict[str, Any]]] = fake_suggest
    #: Bu metinler için yer tutucuları bozulmuş çeviri döner (ilk N istekte).
    break_texts: dict[str, int] = field(default_factory=dict)
    #: Bu metinler yanıtta hiç yer almaz (ilk N istekte).
    drop_texts: dict[str, int] = field(default_factory=dict)
    #: İlk N /api/chat isteği zaman aşımına uğrar.
    timeouts: int = 0
    #: İlk N /api/chat isteği bozuk JSON içerik döndürür.
    bad_json: int = 0
    #: Bu kadar /api/chat isteğinden sonra her istek 500 döner.
    fail_after: int | None = None
    down: bool = False
    #: Bu kadar maddeden büyük partide yanıt uzunluk sınırında kesilir (yarım JSON, bitiş nedeni "length").
    truncate_over: int | None = None
    #: Modelin sohbet şablonu (`ollama show --template`); verilmeyen modelde /api/show şablon alanı döndürmez.
    templates: dict[str, str] = field(default_factory=dict)
    #: Modelin bağlam uzunluğu (`model_info` içindeki `<aile>.context_length`).
    context_lengths: dict[str, int] = field(default_factory=dict)
    #: /api/show çağrılarının model adları (önbellek denetimi için).
    show_calls: list[str] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("bağlantı reddedildi", request=request)
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        if path == "/api/version":
            return httpx.Response(200, json={"version": "0.34.4"})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": self.models})
        if path == "/api/show":
            caps = self.capabilities.get(body.get("model", ""))
            if caps is None:
                return httpx.Response(404, json={"error": f"model '{body.get('model')}' not found"})
            self.show_calls.append(body["model"])
            info: dict[str, Any] = {"capabilities": caps}
            if body["model"] in self.templates:
                info["template"] = self.templates[body["model"]]
            if body["model"] in self.context_lengths:
                info["model_info"] = {
                    "general.architecture": "gemma4",
                    "gemma4.context_length": self.context_lengths[body["model"]],
                }
            return httpx.Response(200, json=info)
        if path == "/api/chat":
            return self._chat(request, body)
        return httpx.Response(404, json={"error": "not found"})

    def _chat(self, request: httpx.Request, body: dict[str, Any]) -> httpx.Response:
        self.requests.append(body)
        n = len(self.requests)
        if self.timeouts > 0:
            self.timeouts -= 1
            raise httpx.ReadTimeout("zaman aşımı", request=request)
        if self.fail_after is not None and n > self.fail_after:
            return httpx.Response(500, json={"error": "internal error"})
        if body.get("model") not in self.capabilities:
            return httpx.Response(404, json={"error": f"model '{body.get('model')}' not found"})
        if self.bad_json > 0:
            self.bad_json -= 1
            return _chat_response(body, "Tabii! İşte çeviri:")
        content = body["messages"][-1]["content"]
        if len(body["messages"]) == 1:  # sistem metni kullanıcı mesajına eklenmiş: "Instructions:…\n\nInput:\n{json}"
            content = content.rsplit("\n\nInput:\n", 1)[1]
        payload = json.loads(content)
        if self.truncate_over is not None and len(payload.get("items", ())) > self.truncate_over:
            return _chat_response(body, '{"translations": [{"id": "0", "te', done_reason="length")
        if "terms" in body["format"]["required"]:
            return _chat_response(body, json.dumps({"terms": self.suggest(payload)}, ensure_ascii=False))
        out = []
        for item in payload["items"]:
            text = item["text"]
            if self.drop_texts.get(text, 0) > 0:
                self.drop_texts[text] -= 1
                continue
            translated = self.revise(item) if "current" in item else self.translate(text)
            if self.break_texts.get(text, 0) > 0:
                self.break_texts[text] -= 1
                translated = re.sub(r"⟦\d+⟧", "", translated)
            out.append({"id": item["id"], "text": translated})
        return _chat_response(body, json.dumps({"translations": out}, ensure_ascii=False))

    def provider(self, model: str = "gemma4:12b") -> OllamaProvider:
        return OllamaProvider(model, client=httpx.Client(transport=httpx.MockTransport(self.handler)))


def _chat_response(body: dict[str, Any], content: str, done_reason: str = "stop") -> httpx.Response:
    """Akış isteğinde Ollama gibi satır satır (NDJSON) parçalar, değilse tek yanıt döner."""
    if not body.get("stream"):
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": content}, "done": True, "done_reason": done_reason}
        )
    step = max(1, len(content) // 3)
    pieces = [content[i : i + step] for i in range(0, len(content), step)] or [""]
    lines = [json.dumps({"message": {"role": "assistant", "content": p}, "done": False}) for p in pieces]
    lines.append(
        json.dumps({"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": done_reason})
    )
    return httpx.Response(200, content="\n".join(lines).encode("utf-8"))
