from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import Settings


class AIBuilderError(RuntimeError):
    pass


@dataclass
class AIBuilderClient:
    settings: Settings

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.settings.v1_base_url + path
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AIBuilderError(f"AI Builder HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise AIBuilderError(f"Could not reach AI Builder: {exc.reason}") from exc

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        schema_hint: str,
        model: str | None = None,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        content = self.chat_text(
            system=system,
            user=f"{user}\n\nReturn only valid JSON matching this shape:\n{schema_hint}",
            model=model,
            max_tokens=max_tokens,
            json_mode=True,
        )
        return parse_json_object(content)

    def chat_text(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 4000,
        json_mode: bool = False,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model or self.settings.chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 1.0,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = self._post_json("/chat/completions", payload)
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise AIBuilderError(f"Unexpected chat response: {data}") from exc
        if choice.get("finish_reason") == "length":
            raise AIBuilderError(
                "Model response was truncated before completion (hit the max_tokens limit "
                f"of {max_tokens}). Retry with a higher max_tokens or shorter input."
            )
        return content

    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        payload = {"model": model or self.settings.embedding_model, "input": texts}
        data = self._post_json("/embeddings", payload)
        try:
            rows = sorted(data["data"], key=lambda item: item["index"])
            return [row["embedding"] for row in rows]
        except (KeyError, TypeError) as exc:
            raise AIBuilderError(f"Unexpected embedding response: {data}") from exc


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(stripped[start : end + 1])
            except json.JSONDecodeError as inner:
                raise _json_error(stripped, inner) from inner
        raise _json_error(stripped, exc) from exc


def _json_error(raw: str, exc: json.JSONDecodeError) -> AIBuilderError:
    lo = max(exc.pos - 120, 0)
    hi = min(exc.pos + 120, len(raw))
    snippet = raw[lo:hi]
    return AIBuilderError(
        f"Model did not return valid JSON ({exc.msg} at line {exc.lineno} "
        f"column {exc.colno}, char {exc.pos}). This usually means the response was "
        f"truncated or malformed. Offending region:\n...{snippet}..."
    )
