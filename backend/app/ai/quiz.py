import json

from agents import Runner, RunConfig

from app.ai.llm import create_agent
from app.ai.prompts import QUIZ_PROMPT
from app.schemas.quiz import GeneratedQuiz


async def generate_quiz(topic: str, passages: list[dict], provider: str = "anthropic") -> GeneratedQuiz:
    agent = create_agent(instructions=QUIZ_PROMPT, output_type=GeneratedQuiz, max_tokens=4096, provider=provider)
    result = await Runner.run(
        agent, json.dumps({"topic": topic, "question_count": 5, "passages": passages}, ensure_ascii=False),
        run_config=RunConfig(tracing_disabled=True),
    )
    return GeneratedQuiz.model_validate(result.final_output)
