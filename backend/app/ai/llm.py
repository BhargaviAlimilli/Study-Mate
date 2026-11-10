import json
import logging
from fastapi import HTTPException

from agents import Agent, ModelSettings, RunConfig, Runner
from agents.extensions.models.litellm_model import LitellmModel
from agents.exceptions import ModelBehaviorError

from app.core.config import get_settings
from app.core.telemetry import event_logger
from app.ai.prompts import STUDY_TUTOR_PROMPT
from app.schemas.chat import TutorAnswer


def ensure_provider_available(provider: str) -> None:
    settings = get_settings()
    configured = {
        "anthropic": bool(settings.anthropic_api_key and settings.anthropic_api_key.get_secret_value().strip()),
        "openai": bool(settings.openai_api_key and settings.openai_model),
        "ollama": bool(settings.ollama_model),
    }
    if not configured.get(provider):
        raise HTTPException(status_code=409, detail=f"The {provider} provider is not configured on this server.")


def create_agent(*, instructions=STUDY_TUTOR_PROMPT, output_type=TutorAnswer, max_tokens=1024, provider="anthropic") -> Agent:
    settings = get_settings()
    ensure_provider_available(provider)
    if provider == "anthropic":
        model = LitellmModel(model=f"anthropic/{settings.anthropic_model}", api_key=settings.anthropic_api_key.get_secret_value())
    elif provider == "openai":
        model = LitellmModel(model=f"openai/{settings.openai_model}", api_key=settings.openai_api_key.get_secret_value())
    else:
        model = LitellmModel(model=f"ollama_chat/{settings.ollama_model}", base_url=settings.ollama_base_url)
    return Agent(name="Study Mate tutor", instructions=instructions, output_type=output_type,
                 model=model, model_settings=ModelSettings(max_tokens=max_tokens))


async def generate_reply(question: str, passages: list[dict], history: list[dict] | None = None, preferences: dict | None = None, action: str = "answer") -> TutorAnswer:
    if not question.strip():
        raise ValueError("The question must not be empty.")
    payload = json.dumps({"question": question, "passages": passages, "history": history or [], "preferences": preferences or {}, "action": action}, ensure_ascii=False)
    for attempt, token_budget in enumerate((2048, 3072)):
        instructions = STUDY_TUTOR_PROMPT
        if attempt:
            instructions += ("\nThe previous attempt did not satisfy the output schema. "
                "Return one complete structured object with status, answer and citation_ids. "
                "Keep the explanation concise (at most 350 words), with no text outside the object. "
                "All original scope and evidence rules still apply.")
        try:
            result = await Runner.run(
                create_agent(instructions=instructions, max_tokens=token_budget,
                             provider=(preferences or {}).get("model_provider", "anthropic")),
                payload,
                # No OpenAI tracing credentials are needed for this Claude-only call.
                run_config=RunConfig(tracing_disabled=True),
            )
            if not isinstance(result.final_output, TutorAnswer):
                raise ModelBehaviorError("The agent returned an invalid answer format.")
            break
        except ModelBehaviorError:
            if attempt:
                raise
            # Do not log malformed output, prompts, or user document contents.
            event_logger('models').warning('tutor_output_retry', extra={'attempt': 1})
    usage = [(getattr(item.usage, "input_tokens", 0), getattr(item.usage, "output_tokens", 0)) for item in result.raw_responses]
    event_logger('models').info('model_usage',extra={'input_tokens':sum(x[0] for x in usage),'output_tokens':sum(x[1] for x in usage)})
    return result.final_output

