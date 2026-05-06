from __future__ import annotations

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

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{input_payload}"),
            ]
        )
        llm = ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            api_key=self.api_key,
            base_url=self.base_url,
        )
        chain = prompt | llm.with_structured_output(schema)

        return chain.invoke({"input_payload": user_payload})
