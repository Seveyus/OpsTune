from __future__ import annotations

import json
import os
from typing import Any, TypeVar

from pydantic import BaseModel


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LangChainBackend:
    """Thin wrapper around LangChain structured-output calls."""

    def __init__(self, model_name: str | None = None, temperature: float = 0.0) -> None:
        self.model_name = model_name or os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        self.temperature = temperature
        self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("FIREWORKS_API_KEY")
        self.base_url = (
            os.getenv("OPENAI_API_BASE")
            or os.getenv("OPENAI_BASE_URL")
            or os.getenv("FIREWORKS_API_BASE")
            or os.getenv("FIREWORKS_BASE_URL")
        )

    def invoke_structured(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema: type[SchemaT],
    ) -> SchemaT:
        try:
            from langchain_core.output_parsers import PydanticOutputParser
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "LangChain dependencies are not installed. Install agent-workflow/requirements.txt "
                "and set your model provider API key before running with mock_mode=False."
            ) from exc

        if not self.api_key:
            raise RuntimeError(
                "Missing API key. Set OPENAI_API_KEY for OpenAI or FIREWORKS_API_KEY for Fireworks."
            )

        parser = PydanticOutputParser(pydantic_object=schema)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        f"{system_prompt.strip()}\n\n"
                        "Return valid JSON only. Do not wrap it in markdown fences.\n"
                        "{format_instructions}"
                    ),
                ),
                ("human", "{input_payload_json}"),
            ]
        )
        llm = ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            api_key=self.api_key,
            base_url=self.base_url,
        )
        chain = prompt | llm | parser

        return chain.invoke(
            {
                "input_payload_json": json.dumps(user_payload, ensure_ascii=True, indent=2),
                "format_instructions": parser.get_format_instructions(),
            }
        )
