"""Adaptateurs des fournisseurs d'IA : le seul endroit où un SDK est importé (ADR-008).

Chaque adaptateur reçoit la consigne commune (ai.SYSTEM_PROMPT), le texte de la pièce et le schéma
strict de réponse, et rend une ai.Completion brute. Toute erreur du fournisseur devient
ai.AIProviderError : le parcours continue sans proposition, en lecture classique et saisie.
"""

import json
import logging

from . import ai

logger = logging.getLogger(__name__)
MAX_OUTPUT_TOKENS = 4000


def _items(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ai.AIProviderError("AI_BAD_OUTPUT", "Réponse de l'IA hors du format attendu : ignorée.") from exc
    items = data.get("fields") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ai.AIProviderError("AI_BAD_OUTPUT", "Réponse de l'IA hors du format attendu : ignorée.")
    return items


def _object(text: str) -> dict:
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ai.AIProviderError("AI_BAD_OUTPUT", "Réponse de l'IA hors du format attendu : ignorée.") from exc
    if not isinstance(data, dict):
        raise ai.AIProviderError("AI_BAD_OUTPUT", "Réponse de l'IA hors du format attendu : ignorée.")
    return data


class AnthropicProvider:
    """Claude, par le SDK officiel « anthropic » : sortie structurée (output_config.format)."""

    name = "anthropic"

    def __init__(self, *, api_key: str, model: str, timeout: int):
        import anthropic

        self._sdk = anthropic
        self.client = anthropic.Anthropic(api_key=api_key, timeout=float(timeout), max_retries=2)
        self.model = model

    def complete_fields(self, *, text, piece, fields):
        prompt = ai.user_prompt(text=text, piece=piece, fields=fields)
        completion = self._generate(ai.SYSTEM_PROMPT, prompt, ai.completion_schema([f.name for f in fields]))
        completion.items = _items(completion.extra.pop("text"))
        return completion

    def choose_code(self, *, description, candidates):
        prompt = ai.choice_prompt(description=description, candidates=candidates)
        completion = self._generate(ai.CLASSIFY_PROMPT, prompt, ai.choice_schema([c["node_id"] for c in candidates]))
        completion.items = [_object(completion.extra.pop("text"))]
        return completion

    def _generate(self, system: str, prompt: str, schema: dict) -> ai.Completion:
        sdk = self._sdk
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            )
        except sdk.AuthenticationError as exc:
            raise ai.AIProviderError("AI_KEY_REJECTED", "Clé du fournisseur d'IA refusée : la vérifier.") from exc
        except sdk.RateLimitError as exc:
            raise ai.AIProviderError("AI_RATE_LIMITED", "Fournisseur d'IA saturé : réessayer plus tard.") from exc
        except sdk.APIConnectionError as exc:
            raise ai.AIProviderError("AI_UNREACHABLE", "Fournisseur d'IA injoignable (internet ?).") from exc
        except sdk.APIStatusError as exc:
            logger.warning("Anthropic : erreur %s", exc.status_code)
            raise ai.AIProviderError("AI_PROVIDER_ERROR", f"Erreur du fournisseur d'IA ({exc.status_code}).") from exc
        if response.stop_reason == "refusal":
            raise ai.AIProviderError("AI_REFUSED", "L'IA a refusé de traiter cette pièce : rien n'est proposé.")
        if response.stop_reason == "max_tokens":
            raise ai.AIProviderError("AI_BAD_OUTPUT", "Réponse de l'IA incomplète : ignorée.")
        text_out = next((b.text for b in response.content if b.type == "text"), "")
        usage = response.usage
        return ai.Completion(
            items=[],
            model=response.model or self.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            stop_reason=response.stop_reason or "",
            extra={"text": text_out},
        )


class GeminiProvider:
    """Gemini, par le SDK officiel « google-genai » : réponse JSON contrainte par le schéma."""

    name = "gemini"

    def __init__(self, *, api_key: str, model: str, timeout: int):
        from google import genai
        from google.genai import types

        self._types = types
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout * 1000))
        self.model = model

    def complete_fields(self, *, text, piece, fields):
        prompt = ai.user_prompt(text=text, piece=piece, fields=fields)
        completion = self._generate(ai.SYSTEM_PROMPT, prompt, ai.completion_schema([f.name for f in fields]))
        completion.items = _items(completion.extra.pop("text"))
        return completion

    def choose_code(self, *, description, candidates):
        prompt = ai.choice_prompt(description=description, candidates=candidates)
        completion = self._generate(ai.CLASSIFY_PROMPT, prompt, ai.choice_schema([c["node_id"] for c in candidates]))
        completion.items = [_object(completion.extra.pop("text"))]
        return completion

    def _generate(self, system: str, prompt: str, schema: dict) -> ai.Completion:
        from google.genai import errors

        types = self._types
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_json_schema=schema,
                    temperature=0,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                ),
            )
        except errors.APIError as exc:
            code = getattr(exc, "code", None)
            if code in (401, 403):
                raise ai.AIProviderError("AI_KEY_REJECTED", "Clé du fournisseur d'IA refusée : la vérifier.") from exc
            if code == 429:
                raise ai.AIProviderError("AI_RATE_LIMITED", "Fournisseur d'IA saturé : réessayer plus tard.") from exc
            logger.warning("Gemini : erreur %s", code)
            raise ai.AIProviderError("AI_PROVIDER_ERROR", f"Erreur du fournisseur d'IA ({code}).") from exc
        except Exception as exc:  # réseau, délai dépassé : le SDK laisse passer les erreurs httpx
            logger.warning("Gemini injoignable : %s", type(exc).__name__)
            raise ai.AIProviderError("AI_UNREACHABLE", "Fournisseur d'IA injoignable (internet ?).") from exc
        usage = response.usage_metadata
        output = None
        if usage is not None and usage.candidates_token_count is not None:
            output = usage.candidates_token_count + (usage.thoughts_token_count or 0)
        return ai.Completion(
            items=[],
            model=self.model,
            input_tokens=usage.prompt_token_count if usage is not None else None,
            output_tokens=output,
            extra={"text": response.text},
        )


def build(name: str, *, api_key: str, model: str, timeout: int):
    adapters = {"anthropic": AnthropicProvider, "gemini": GeminiProvider}
    try:
        return adapters[name](api_key=api_key, model=model, timeout=timeout)
    except ImportError as exc:
        raise ai.AIProviderError("AI_SDK_MISSING", "Bibliothèque du fournisseur d'IA absente du serveur.") from exc
