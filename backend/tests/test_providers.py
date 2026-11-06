from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from app.ai import llm
from app.routes import media


@pytest.mark.parametrize('provider',['anthropic','openai','ollama'])
def test_unconfigured_provider_has_clear_error(monkeypatch,provider):
    settings=SimpleNamespace(anthropic_api_key=None,openai_api_key=None,openai_model=None,ollama_model=None)
    monkeypatch.setattr(llm,'get_settings',lambda:settings)
    with pytest.raises(HTTPException) as error:
        llm.ensure_provider_available(provider)
    assert error.value.status_code == 409


@pytest.mark.parametrize('provider,prefix',[('anthropic','anthropic/'),('openai','openai/'),('ollama','ollama_chat/')])
def test_provider_adapter_selection_without_model_calls(monkeypatch,provider,prefix):
    settings=SimpleNamespace(anthropic_api_key=SecretStr('test-key'),anthropic_model='test-claude',
        openai_api_key=SecretStr('test-key'),openai_model='test-openai',ollama_model='test-local',ollama_base_url='http://127.0.0.1:11434')
    monkeypatch.setattr(llm,'get_settings',lambda:settings)
    agent=llm.create_agent(provider=provider)
    assert agent.model.model.startswith(prefix)
    if provider == 'ollama':
        assert agent.model.base_url == settings.ollama_base_url


def test_voice_requires_its_own_provider_key(monkeypatch):
    monkeypatch.setattr(media,'get_settings',lambda:SimpleNamespace(openai_api_key=None))
    with pytest.raises(HTTPException) as error:
        media.speech_client()
    assert error.value.status_code == 409
