import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agents.exceptions import ModelBehaviorError

from app.ai import llm
from app.schemas.chat import TutorAnswer


def test_invalid_structured_output_gets_one_validated_retry(monkeypatch):
    answer = TutorAnswer(status='answered', answer='Await yields control.', citation_ids=[1])
    runner = AsyncMock(side_effect=[ModelBehaviorError('Incomplete JSON'),
        SimpleNamespace(final_output=answer, raw_responses=[])])
    agent = Mock()
    monkeypatch.setattr(llm.Runner, 'run', runner)
    monkeypatch.setattr(llm, 'create_agent', agent)
    result = asyncio.run(llm.generate_reply('Explain await', [{'citation_id': 1, 'text': 'Await yields.'}]))
    assert result == answer
    assert runner.await_count == 2
    assert runner.await_args_list[0].args[1] == runner.await_args_list[1].args[1]
    assert agent.call_args_list[1].kwargs['max_tokens'] > agent.call_args_list[0].kwargs['max_tokens']
    assert 'original scope and evidence rules' in agent.call_args_list[1].kwargs['instructions']


def test_persistent_output_failure_is_bounded(monkeypatch):
    runner = AsyncMock(side_effect=ModelBehaviorError('Invalid schema'))
    monkeypatch.setattr(llm.Runner, 'run', runner)
    monkeypatch.setattr(llm, 'create_agent', Mock())
    with pytest.raises(ModelBehaviorError):
        asyncio.run(llm.generate_reply('Explain await', []))
    assert runner.await_count == 2


def test_transport_errors_are_not_retried_as_format_errors(monkeypatch):
    runner = AsyncMock(side_effect=ConnectionError('Provider unavailable'))
    monkeypatch.setattr(llm.Runner, 'run', runner)
    monkeypatch.setattr(llm, 'create_agent', Mock())
    with pytest.raises(ConnectionError):
        asyncio.run(llm.generate_reply('Explain await', []))
    assert runner.await_count == 1
