import asyncio
import sys

from agents import Agent, ModelSettings, RunConfig, Runner
from agents.extensions.models.litellm_model import LitellmModel

from app.core.config import get_settings


def create_agent() -> Agent:
    settings = get_settings()
    if settings.anthropic_api_key is None or not settings.anthropic_api_key.get_secret_value().strip():
        raise ValueError("Set ANTHROPIC_API_KEY in backend/.env before calling Claude.")

    return Agent(
        name="History tutor",
        instructions="You answer history questions clearly and concisely.",
        model=LitellmModel(
            model=f"anthropic/{settings.anthropic_model}",
            api_key=settings.anthropic_api_key.get_secret_value(),
        ),
        model_settings=ModelSettings(max_tokens=1024),
    )


async def generate_reply(question: str) -> str:
    if not question.strip():
        raise ValueError("The question must not be empty.")
    result = await Runner.run(
        create_agent(),
        question,
        # No OpenAI tracing credentials are needed for this Claude-only call.
        run_config=RunConfig(tracing_disabled=True),
    )
    return str(result.final_output)

