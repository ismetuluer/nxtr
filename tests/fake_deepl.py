"""Testler için sahte DeepL API'si (httpx.MockTransport; ağ kullanmaz)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from nxceviri.core.translate.providers.deepl import DeepLProvider

FREE_KEY = "00000000-test-anahtar-0000-000000000000:fx"
PRO_KEY = "00000000-test-anahtar-0000-000000000000"


def fake_deepl_translate(xml: str) -> str:
    """Etiketlere dokunmadan sözcüklerin başına "tr-" ekler; ilk etiketi sona taşımaz."""
    return re.sub(r"(?<![<\w=\"/&])([A-Za-z]+)(?![^<]*>)", r"tr-\1", xml)


@dataclass
class FakeDeepL:
    used: int = 1000
    limit: int = 500_000
    status: int | None = None  # verilirse her istek bu kodla döner
    translate_status: list[int] = field(default_factory=list)  # sırayla /v2/translate yanıt kodları
    move_tags: bool = False  # True: etiketleri cümlenin başına taşır (sıra bozulur)
    glossary_error: int | None = None
    requests: list[tuple[str, str, dict[str, Any], str]] = field(default_factory=list)
    glossaries: dict[str, str] = field(default_factory=dict)
    counter: int = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        auth = request.headers.get("Authorization", "")
        self.requests.append((request.method, request.url.path, body, str(request.url.host)))
        if not auth.startswith("DeepL-Auth-Key "):
            return httpx.Response(403, json={"message": "Authorization failure"})
        if self.status is not None:
            return httpx.Response(self.status, json={"message": "zorla"})
        path = request.url.path
        if path == "/v2/usage":
            return httpx.Response(200, json={"character_count": self.used, "character_limit": self.limit})
        if path == "/v2/glossaries" and request.method == "POST":
            if self.glossary_error:
                return httpx.Response(self.glossary_error, json={"message": "Unsupported language pair"})
            self.counter += 1
            gid = f"sozluk-{self.counter}"
            self.glossaries[gid] = body["entries"]
            return httpx.Response(
                201, json={"glossary_id": gid, "ready": True, "entry_count": body["entries"].count("\n") + 1}
            )
        if path.startswith("/v2/glossaries/") and request.method == "DELETE":
            self.glossaries.pop(path.rsplit("/", 1)[-1], None)
            return httpx.Response(204)
        if path == "/v2/translate":
            if self.translate_status:
                code = self.translate_status.pop(0)
                if code != 200:
                    return httpx.Response(code, json={"message": "geçici"})
            out = []
            for text in body["text"]:
                translated = fake_deepl_translate(text)
                if self.move_tags:
                    tags = re.findall(r"<x[^>]*/>", translated)
                    translated = "".join(reversed(tags)) + re.sub(r"<x[^>]*/>", "", translated)
                out.append({"text": translated, "detected_source_language": "EN"})
            self.used += sum(len(t) for t in body["text"])
            return httpx.Response(200, json={"translations": out})
        return httpx.Response(404, json={"message": "not found"})

    def provider(self, key: str = FREE_KEY) -> DeepLProvider:
        return DeepLProvider(key, client=httpx.Client(transport=httpx.MockTransport(self.handler)))
