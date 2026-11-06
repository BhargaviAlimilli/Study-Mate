import json

from agents import Agent, ModelSettings, RunConfig, Runner
from agents.extensions.models.litellm_model import LitellmModel

from app.core.config import get_settings
from app.ai.prompts import STUDY_TUTOR_PROMPT
from app.schemas.chat import TutorAnswer


def create_agent() -> Agent:
    settings = get_settings()
    if settings.anthropic_api_key is None or not settings.anthropic_api_key.get_secret_value().strip():
        raise ValueError("Set ANTHROPIC_API_KEY in backend/.env before calling Claude.")

    return Agent(
        name="Study Mate tutor",
        instructions=STUDY_TUTOR_PROMPT,
        output_type=TutorAnswer,
        model=LitellmModel(
            model=f"anthropic/{settings.anthropic_model}",
            api_key=settings.anthropic_api_key.get_secret_value(),
        ),
        model_settings=ModelSettings(max_tokens=1024),
    )


async def generate_reply(question: str, passages: list[dict], history: list[dict] | None = None) -> TutorAnswer:
    if not question.strip():
        raise ValueError("The question must not be empty.")
    result = await Runner.run(
        create_agent(),
        json.dumps({"question": question, "passages": passages, "history": history or []}, ensure_ascii=False),
        # No OpenAI tracing credentials are needed for this Claude-only call.
        run_config=RunConfig(tracing_disabled=True),
    )
    if not isinstance(result.final_output, TutorAnswer):
        raise ValueError("The agent returned an invalid answer format.")
    return result.final_output

