from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.core.security import get_current_user
from app.main import app
from app.schemas.chat import TutorAnswer
from app.services import chat_service
from app.ai.vectorstore import MissingCollectionError


@pytest.fixture
def chat(monkeypatch):
    owner = uuid4()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=owner)
    retrieval = []
    def retrieve(query, *, user_id, k):
        retrieval.append((query, user_id))
        return [Document(page_content='A list is mutable.', metadata={
            'document_id': 'doc-1', 'filename': 'notes.pdf', 'page': 2
        })]
    monkeypatch.setattr(chat_service, 'get_document_embeddings', retrieve)
    agent = AsyncMock(return_value=TutorAnswer(
        status='answered', answer='You can change list elements. [1]', citation_ids=[1]
    ))
    monkeypatch.setattr(chat_service, 'generate_reply', agent)
    try:
        with TestClient(app) as client:
            yield client, owner, retrieval, agent
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_grounded_query_and_user_scope(chat):
    client, owner, retrieval, agent = chat
    response = client.post('/query', json={'query': '  Explain mutable lists  '})
    assert response.status_code == 200
    assert retrieval == [('Explain mutable lists', str(owner))]
    assert response.json()['sources'][0]['page'] == 2
    assert response.json()['sources'][0]['document_id'] == 'doc-1'
    assert agent.call_args.args[1] == [{'citation_id': 1, 'text': 'A list is mutable.'}]


@pytest.mark.parametrize('payload', [{}, {'query': ' '}, {'query': 'x' * 4001}, {'query': 'ok', 'user_id': 'another-user'}])
def test_validation(chat, payload):
    assert chat[0].post('/query', json=payload).status_code == 422
    chat[3].assert_not_called()


@pytest.mark.parametrize('status', ['out_of_scope', 'insufficient_context', 'quiz_unavailable'])
def test_agent_response_statuses(chat, status):
    chat[3].return_value = TutorAnswer(status=status, answer='Please ask about your notes.', citation_ids=[])
    response = chat[0].post('/query', json={'query': 'A question'})
    assert response.json()['status'] == status
    assert response.json()['sources'] == []


def test_no_documents_and_missing_collection(chat, monkeypatch):
    monkeypatch.setattr(chat_service, 'get_document_embeddings', lambda *args, **kwargs: [])
    assert chat[0].post('/query', json={'query': 'Explain lists'}).json()['status'] == 'insufficient_context'
    def missing(*args, **kwargs):
        raise MissingCollectionError()
    monkeypatch.setattr(chat_service, 'get_document_embeddings', missing)
    assert chat[0].post('/query', json={'query': 'Explain lists'}).status_code == 200
    chat[3].assert_not_called()


def test_invalid_citation_and_provider_errors(chat, monkeypatch):
    chat[3].return_value = TutorAnswer(status='answered', answer='Invented answer [99]', citation_ids=[99])
    assert chat[0].post('/query', json={'query': 'Explain lists'}).json()['status'] == 'insufficient_context'
    chat[3].side_effect = RuntimeError('private provider details')
    response = chat[0].post('/query', json={'query': 'Explain lists'})
    assert response.status_code == 503
    assert 'private provider details' not in response.text
    chat[3].side_effect = TimeoutError()
    assert chat[0].post('/query', json={'query': 'Explain lists'}).status_code == 504
    def fail(*args, **kwargs):
        raise RuntimeError('private connection details')
    monkeypatch.setattr(chat_service, 'get_document_embeddings', fail)
    assert chat[0].post('/query', json={'query': 'Explain lists'}).status_code == 503


def test_query_requires_authentication():
    with TestClient(app) as client:
        assert client.post('/query', json={'query': 'Explain lists'}).status_code == 401
