"""Adaptateurs Claude et Gemini (T67) : vraie bibliothèque du fournisseur, serveur HTTP local factice.

Aucune requête ne sort de la machine : l'adresse du fournisseur est remplacée par un serveur local
qui enregistre la requête reçue et rend une réponse au format du fournisseur.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from apps.extraction import ai, ai_providers

FIELDS = [ai.FieldRequest("packages", "Colis"), ai.FieldRequest("measurement", "Volume")]
ANSWER = {"fields": [{"field": "packages", "found": True, "value": "12 PALLETS", "excerpt": "12 PALLETS"},
                     {"field": "measurement", "found": False, "value": "", "excerpt": ""}]}  # fmt: skip


@pytest.fixture
def server(monkeypatch):
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(name, "127.0.0.1,localhost")  # le serveur local ne passe jamais par un proxy
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - nom imposé par http.server
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.update(path=self.path, body=body, headers={k.lower(): v for k, v in self.headers.items()})
            reply = seen["reply"](self.path)
            data = json.dumps(reply["json"]).encode()
            self.send_response(reply.get("status", 200))
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", seen
    httpd.shutdown()


def test_t67_claude_adapter_sends_text_and_strict_schema(server):
    url, seen = server
    seen["reply"] = lambda path: {"json": {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": json.dumps(ANSWER)}],
        "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 321, "output_tokens": 45},
    }}  # fmt: skip
    provider = ai_providers.build("anthropic", api_key="cle-de-test", model="claude-haiku-5-5", timeout=5)
    provider.client = provider.client.with_options(base_url=url, max_retries=0)
    result = provider.complete_fields(text="[page 1]\nTotal 12 PALLETS", piece="titre de transport", fields=FIELDS)
    assert seen["path"] == "/v1/messages" and seen["headers"]["authorization"] == "Bearer cle-de-test"
    body = seen["body"]
    assert body["model"] == "claude-haiku-5-5" and body["system"] == ai.SYSTEM_PROMPT
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["format"]["schema"] == ai.completion_schema(["packages", "measurement"])
    assert "<piece>\n[page 1]\nTotal 12 PALLETS\n</piece>" in body["messages"][0]["content"]
    assert result.items == ANSWER["fields"] and (result.input_tokens, result.output_tokens) == (321, 45)


def test_t67_claude_refusal_and_bad_key_become_provider_errors(server):
    url, seen = server
    provider = ai_providers.build("anthropic", api_key="k", model="claude-haiku-5-5", timeout=5)
    provider.client = provider.client.with_options(base_url=url, max_retries=0)
    seen["reply"] = lambda path: {"json": {
        "id": "m", "type": "message", "role": "assistant", "model": "claude-haiku-5-5", "content": [],
        "stop_reason": "refusal", "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 0},
    }}  # fmt: skip
    with pytest.raises(ai.AIProviderError) as exc:
        provider.complete_fields(text="x", piece="p", fields=FIELDS)
    assert exc.value.code == "AI_REFUSED"
    seen["reply"] = lambda path: {"status": 401, "json": {
        "type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}}  # fmt: skip
    with pytest.raises(ai.AIProviderError) as exc:
        provider.complete_fields(text="x", piece="p", fields=FIELDS)
    assert exc.value.code == "AI_KEY_REJECTED"


def test_t67_gemini_adapter_sends_text_and_json_schema(server):
    url, seen = server
    seen["reply"] = lambda path: {"json": {
        "candidates": [{"content": {"parts": [{"text": json.dumps(ANSWER)}], "role": "model"}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 300, "candidatesTokenCount": 40, "totalTokenCount": 340},
    }}  # fmt: skip
    from google.genai import types

    provider = ai_providers.build("gemini", api_key="cle-gemini", model="gemini-3.5-flash-lite", timeout=5)
    provider.client = __import__("google.genai", fromlist=["Client"]).Client(
        api_key="cle-gemini", http_options=types.HttpOptions(base_url=url, timeout=5000)
    )
    result = provider.complete_fields(text="[page 1]\nTotal 12 PALLETS", piece="titre de transport", fields=FIELDS)
    assert seen["path"].endswith("/models/gemini-3.5-flash-lite:generateContent")
    assert seen["headers"]["x-goog-api-key"] == "cle-gemini"
    body = seen["body"]
    assert body["systemInstruction"]["parts"][0]["text"] == ai.SYSTEM_PROMPT
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseJsonSchema"] == ai.completion_schema(["packages", "measurement"])
    assert "Total 12 PALLETS" in body["contents"][0]["parts"][0]["text"]
    assert result.items == ANSWER["fields"] and (result.input_tokens, result.output_tokens) == (300, 40)


def test_t67_gemini_error_becomes_provider_error(server):
    url, seen = server
    from google import genai
    from google.genai import types

    provider = ai_providers.build("gemini", api_key="k", model="gemini-3.5-flash-lite", timeout=5)
    provider.client = genai.Client(api_key="k", http_options=types.HttpOptions(base_url=url, timeout=5000))
    seen["reply"] = lambda path: {
        "status": 429,
        "json": {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}},
    }
    with pytest.raises(ai.AIProviderError) as exc:
        provider.complete_fields(text="x", piece="p", fields=FIELDS)
    assert exc.value.code == "AI_RATE_LIMITED"
