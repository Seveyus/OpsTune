"""HuggingFace backend that uses a local OpenAI-compatible model server."""

from __future__ import annotations

import json
import os
import re
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from .schemas import (
    ActionPlanResult,
    IncidentFacts,
    RecommendedAction,
    RootCauseHypothesis,
    RootCauseResult,
    TriageResult,
    WorkflowResult,
)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class HuggingFaceBackend:
    """Backend that calls a local HuggingFace model server through an OpenAI-compatible API.

    The local model is useful for demos, but it may occasionally return malformed or truncated JSON.
    This backend therefore treats the LLM as an unreliable text generator and guarantees that callers
    still receive a valid Pydantic object.
    """

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float = 0.0,
        base_url: str | None = None,
    ) -> None:
        self.model_name = model_name or os.getenv("OPENAI_MODEL", "opstune")
        self.temperature = temperature
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL") or "http://localhost:8000/v1"
        self.api_key = os.getenv("OPENAI_API_KEY", "dummy")

    def invoke_structured(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema: type[SchemaT],
        max_retries: int = 2,
    ) -> SchemaT:
        """Call the local model and return a valid object matching the requested schema.

        If the model returns malformed/truncated JSON, retry with a stricter prompt. If it still fails,
        return a deterministic schema-aware fallback so the API never crashes during LLM mode.
        """
        prompt = self._build_prompt(
            system_prompt=system_prompt,
            user_payload=user_payload,
            schema=schema,
        )

        last_error: Exception | None = None
        last_raw = ""

        for attempt in range(max_retries + 1):
            try:
                raw = self._call_model(prompt)
                last_raw = raw
                payload = self._parse_json_object(raw)
                normalized_payload = self._normalize_payload(payload=payload, schema=schema, user_payload=user_payload)
                return schema.model_validate(normalized_payload)
            except Exception as exc:
                last_error = exc
                prompt = self._build_retry_prompt(
                    system_prompt=system_prompt,
                    user_payload=user_payload,
                    schema=schema,
                    previous_error=str(exc),
                )

        return self._fallback_for_schema(
            schema=schema,
            user_payload=user_payload,
            reason=f"{last_error}. Raw response preview: {last_raw[:500]}",
        )

    def _build_prompt(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema: type[BaseModel],
    ) -> str:
        return (
            f"{system_prompt.strip()}\n\n"
            "You must return ONLY one valid JSON object.\n"
            "Do not use markdown fences.\n"
            "Do not include explanations.\n"
            "Do not repeat values.\n"
            "Keep every list short: maximum 5 items.\n"
            "Close all strings, arrays, and objects.\n\n"
            f"Required JSON schema:\n{json.dumps(schema.model_json_schema(), ensure_ascii=False)}\n\n"
            f"Input payload:\n{json.dumps(user_payload, ensure_ascii=False, indent=2)}"
        )

    def _build_retry_prompt(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema: type[BaseModel],
        previous_error: str,
    ) -> str:
        return (
            f"{system_prompt.strip()}\n\n"
            "The previous answer was invalid JSON.\n"
            f"Parser error: {previous_error}\n\n"
            "Return ONLY a compact valid JSON object matching the schema below.\n"
            "Rules:\n"
            "- No markdown.\n"
            "- No comments.\n"
            "- No repeated list items.\n"
            "- Maximum 3 items per list.\n"
            "- All strings must be closed.\n"
            "- The response must start with '{' and end with '}'.\n\n"
            f"Required JSON schema:\n{json.dumps(schema.model_json_schema(), ensure_ascii=False)}\n\n"
            f"Input payload:\n{json.dumps(user_payload, ensure_ascii=False, indent=2)}"
        )

    def _call_model(self, prompt: str) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    "temperature": self.temperature,
                    "max_tokens": 1536,
                    "repetition_penalty": 1.15,
                    "frequency_penalty": 0.4,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Failed to connect to model server at {self.base_url}. "
                "Make sure the local model server is running."
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Model server returned an unexpected response format.") from exc

    def _parse_json_object(self, text: str) -> dict[str, Any]:
        cleaned = self._strip_markdown_fences(text).strip()

        try:
            value = json.loads(cleaned)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass

        extracted = self._extract_first_balanced_json_object(cleaned)
        if extracted is not None:
            value = json.loads(extracted)
            if isinstance(value, dict):
                return value

        repaired = self._repair_simple_truncation(cleaned)
        value = json.loads(repaired)
        if not isinstance(value, dict):
            raise ValueError("Model response is valid JSON, but it is not a JSON object.")
        return value

    def _strip_markdown_fences(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json|python)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        return text.strip()

    def _extract_first_balanced_json_object(self, text: str) -> str | None:
        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape = False

        for index in range(start, len(text)):
            char = text[index]

            if escape:
                escape = False
                continue

            if char == "\\":
                escape = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]

        return None

    def _repair_simple_truncation(self, text: str) -> str:
        candidate = text.strip()

        start = candidate.find("{")
        if start > 0:
            candidate = candidate[start:]

        if not candidate.startswith("{"):
            raise ValueError("Model response does not contain a JSON object.")

        candidate = self._cut_after_last_safe_separator(candidate)

        if self._has_unclosed_string(candidate):
            candidate += '"'

        open_square = candidate.count("[") - candidate.count("]")
        open_curly = candidate.count("{") - candidate.count("}")

        if open_square > 0:
            candidate += "]" * open_square

        if open_curly > 0:
            candidate += "}" * open_curly

        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        return candidate

    def _cut_after_last_safe_separator(self, text: str) -> str:
        in_string = False
        escape = False
        last_safe_index = -1

        for index, char in enumerate(text):
            if escape:
                escape = False
                continue

            if char == "\\":
                escape = True
                continue

            if char == '"':
                in_string = not in_string
                if not in_string:
                    last_safe_index = index
                continue

            if not in_string and char in ",]}":
                last_safe_index = index

        if last_safe_index == -1:
            return text

        if self._has_unclosed_string(text):
            return text[: last_safe_index + 1].rstrip(", ")

        return text

    def _has_unclosed_string(self, text: str) -> bool:
        in_string = False
        escape = False

        for char in text:
            if escape:
                escape = False
                continue

            if char == "\\":
                escape = True
                continue

            if char == '"':
                in_string = not in_string

        return in_string

    def _normalize_payload(
        self,
        *,
        payload: dict[str, Any],
        schema: type[SchemaT],
        user_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if schema is IncidentFacts:
            incident_report = str(user_payload.get("incident_report", ""))
            payload["raw_report"] = self._coerce_raw_report(payload.get("raw_report"), incident_report)
            payload["normalized_report"] = str(payload.get("normalized_report") or incident_report).strip()
            payload["equipment"] = self._short_string_list(payload.get("equipment"))
            payload["symptoms"] = self._short_string_list(payload.get("symptoms"))
            payload["observed_anomalies"] = self._short_string_list(payload.get("observed_anomalies"))
            payload["operational_impact"] = self._short_string_list(payload.get("operational_impact"))
            payload["extracted_signals"] = self._short_string_list(payload.get("extracted_signals"))

        if schema is RootCauseResult:
            causes = payload.get("likely_root_causes", [])
            if not isinstance(causes, list):
                causes = []
            payload["likely_root_causes"] = causes[:3]
            payload["evidence"] = self._short_string_list(payload.get("evidence"))

        if schema is ActionPlanResult:
            actions = payload.get("actions", [])
            if not isinstance(actions, list):
                actions = []
            payload["actions"] = actions[:5]

        return payload

    def _coerce_raw_report(self, value: Any, fallback: str) -> str:
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
                if isinstance(decoded, dict) and isinstance(decoded.get("incident_report"), str):
                    return decoded["incident_report"]
            except json.JSONDecodeError:
                return value
            return value

        return fallback

    def _short_string_list(self, value: Any, limit: int = 5) -> list[str]:
        if not isinstance(value, list):
            return []

        result: list[str] = []
        seen: set[str] = set()

        for item in value:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
            if len(result) >= limit:
                break

        return result

    def _fallback_for_schema(
        self,
        *,
        schema: type[SchemaT],
        user_payload: dict[str, Any],
        reason: str,
    ) -> SchemaT:
        if schema is IncidentFacts:
            incident_report = str(user_payload.get("incident_report", ""))
            normalized_report = " ".join(incident_report.strip().split())
            lower_report = normalized_report.lower()

            equipment = [
                word
                for word in ["pump", "motor", "bearing", "conveyor", "compressor", "spindle", "hydraulic"]
                if word in lower_report
            ]

            symptoms = [
                word
                for word in ["vibration", "overheating", "leak", "smell", "noise", "alarm", "shutdown", "trip"]
                if word in lower_report
            ]

            impact = [
                phrase
                for phrase in ["downtime", "stopped", "production loss", "scrap", "reduced throughput"]
                if phrase in lower_report
            ]

            signals = [
                word
                for word in ["temperature", "pressure", "current", "sensor", "code", "error"]
                if word in lower_report
            ]

            return schema.model_validate(
                IncidentFacts(
                    raw_report=incident_report,
                    normalized_report=normalized_report,
                    equipment=equipment or ["machine"],
                    symptoms=symptoms,
                    observed_anomalies=["LLM output was invalid; deterministic extraction used"],
                    operational_impact=impact,
                    extracted_signals=signals,
                ).model_dump()
            )

        if schema is TriageResult:
            return schema.model_validate(
                TriageResult(
                    severity="medium",
                    category="unknown",
                    urgency="medium",
                    rationale="LLM output was invalid; safe default triage was used.",
                ).model_dump()
            )

        if schema is RootCauseResult:
            return schema.model_validate(
                RootCauseResult(
                    likely_root_causes=[
                        RootCauseHypothesis(
                            cause="General process instability requiring inspection",
                            likelihood=0.5,
                            evidence=["LLM output was invalid; safe fallback root cause was used"],
                        )
                    ],
                    evidence=["LLM output was invalid; deterministic fallback used"],
                ).model_dump()
            )

        if schema is ActionPlanResult:
            return schema.model_validate(
                ActionPlanResult(
                    actions=[
                        RecommendedAction(
                            priority="next_shift",
                            action="Inspect the affected asset and verify operating readings.",
                            owner="maintenance",
                            reason="LLM output was invalid; safe fallback action was used.",
                        )
                    ]
                ).model_dump()
            )

        if schema is WorkflowResult:
            return schema.model_validate(
                WorkflowResult(
                    severity="medium",
                    category="unknown",
                    likely_root_causes=["General process instability requiring inspection"],
                    evidence=["LLM output was invalid; deterministic fallback used"],
                    recommended_actions=["Inspect the affected asset and verify operating readings."],
                    confidence=0.5,
                    final_report="The LLM response was invalid, so OpsTune returned a safe deterministic analysis.",
                ).model_dump()
            )

        try:
            return schema.model_validate({})
        except ValidationError as exc:
            raise RuntimeError(f"Cannot build fallback for schema {schema.__name__}: {reason}") from exc
