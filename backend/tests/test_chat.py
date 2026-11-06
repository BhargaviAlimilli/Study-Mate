from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.core.security import get_current_user
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.models.user import User
from app.models.document import DocumentRecord
from app.models.conversation import Conversation, Message
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.main import app
from app.schemas.chat import TutorAnswer
from app.services import chat_service
from app.ai.vectorstore import MissingCollectionError
from app.ai import graph as chat_graph
from sqlalchemy.engine import make_url


@pytest.fixture
def chat(monkeypatch):
    schema = 'test_chat_' + uuid4().hex
    engine = create_engine(get_settings().database_url)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(test_engine)
    checkpoint_uri = make_url(get_settings().database_url).set(drivername='postgresql').update_query_dict({'options': f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    monkeypatch.setattr(chat_graph, 'get_checkpoint_uri', lambda: checkpoint_uri)
    chat_graph.setup_checkpointer()
    owner = uuid4()
    with Session(test_engine) as db:
        db.add(User(id=owner, name='Chat test', email='chat@example.com', password_hash='test-only'))
        db.flush()
        document_id = uuid4()
        db.add(DocumentRecord(id=document_id, user_id=owner, filename='notes.pdf', pdf_content=b'test', size_bytes=4, page_count=2, chunks_stored=1, status='ready'))
        db.commit()
    def test_db():
        with Session(test_engine, expire_on_commit=False) as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=owner)
    retrieval = []
    def retrieve(query, *, user_id, k, **kwargs):
        retrieval.append((query, user_id))
        return [Document(page_content='A list is mutable.', metadata={
            'document_id': str(document_id), 'filename': 'notes.pdf', 'page': 2
        })]
    monkeypatch.setattr(chat_service, 'get_document_embeddings', retrieve)
    agent = AsyncMock(return_value=TutorAnswer(
        status='answered', answer='You can change list elements.', citation_ids=[1]
    ))
    monkeypatch.setattr(chat_service, 'generate_reply', agent)
    try:
        with TestClient(app) as client:
            yield client, owner, retrieval, agent
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_grounded_query_and_user_scope(chat):
    client, owner, retrieval, agent = chat
    response = client.post('/query', json={'query': '  Explain mutable lists  '})
    assert response.status_code == 200
    assert retrieval == [('Explain mutable lists', str(owner))]
    assert response.json()['status'] == 'answered'
    assert response.json()['answer'] == 'You can change list elements.'
    UUID(response.json()['conversation_id'])
    assert 'citation_ids' not in response.json()
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
    assert set(response.json()) == {'status', 'answer', 'conversation_id', 'request_id'}


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


def test_resume_conversation_and_ownership(chat):
    client, owner, retrieval, agent = chat
    first = client.post('/query', json={'query': 'Explain mutable lists'}).json()
    conversation_id = first['conversation_id']
    second = client.post('/query', json={'query': 'Give me another example', 'conversation_id': conversation_id})
    assert second.status_code == 200
    assert second.json()['conversation_id'] == conversation_id
    assert 'Explain mutable lists' in retrieval[-1][0]
    assert agent.call_args.kwargs['history'] == [
        {'role': 'user', 'content': 'Explain mutable lists'},
        {'role': 'assistant', 'content': 'You can change list elements.'},
    ]
    # Every request opens a fresh SQLAlchemy session: no in-memory chat cache.
    saved = client.get(f'/conversations/{conversation_id}/messages').json()
    assert [message['sequence'] for message in saved] == [1, 2, 3, 4]
    assert [message['role'] for message in saved] == ['user', 'assistant', 'user', 'assistant']
    assert client.get('/conversations').json()[0]['id'] == conversation_id
    assert client.get(f'/conversations/{conversation_id}').status_code == 200
    before = len(retrieval)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    assert client.get('/conversations').json() == []
    assert client.get(f'/conversations/{conversation_id}/messages').status_code == 404
    assert client.post('/query', json={'query': 'Continue', 'conversation_id': conversation_id}).status_code == 404
    assert len(retrieval) == before


def test_failure_does_not_save_half_turn(chat):
    client, _, _, agent = chat
    conversation_id = client.post('/query', json={'query': 'Explain lists'}).json()['conversation_id']
    agent.side_effect = RuntimeError('failure')
    assert client.post('/query', json={'query': 'Another example', 'conversation_id': conversation_id}).status_code == 503
    assert len(client.get(f'/conversations/{conversation_id}/messages').json()) == 2
    assert client.post('/query', json={'query': 'New topic'}).status_code == 503
    assert len(client.get('/conversations').json()) == 1


def test_stale_checkpoint_is_rejected(chat):
    from app.ai.memory import load_context, save_turn
    from app.schemas.chat import ChatResponse
    from fastapi import HTTPException
    client, owner, _, _ = chat
    conversation_id = UUID(client.post('/query', json={'query': 'Explain lists'}).json()['conversation_id'])
    first_db = app.dependency_overrides[get_db]()
    second_db = app.dependency_overrides[get_db]()
    db1, db2 = next(first_db), next(second_db)
    try:
        first_context = load_context(db1, owner, conversation_id)
        stale_context = load_context(db2, owner, conversation_id)
        response = ChatResponse(status='answered', answer='Example')
        save_turn(db1, owner, first_context, 'First continuation', response)
        with pytest.raises(HTTPException) as error:
            save_turn(db2, owner, stale_context, 'Conflicting continuation', response)
        assert error.value.status_code == 409
        assert len(client.get(f'/conversations/{conversation_id}/messages').json()) == 4
    finally:
        first_db.close()
        second_db.close()


def test_history_restores_in_a_fresh_python_process(chat):
    import os
    import subprocess
    import sys
    from pathlib import Path
    client, owner, _, _ = chat
    conversation_id = client.post('/query', json={'query': 'Explain lists'}).json()['conversation_id']
    database = app.dependency_overrides[get_db]()
    db = next(database)
    schema = db.get_bind().get_execution_options()['schema_translate_map'][None]
    database.close()
    code = """
import os
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.ai.memory import load_context
engine = create_engine(get_settings().database_url).execution_options(schema_translate_map={None: os.environ['TEST_CHAT_SCHEMA']})
with Session(engine) as db:
    context = load_context(db, UUID(os.environ['TEST_CHAT_USER']), UUID(os.environ['TEST_CHAT_CONVERSATION']))
    assert context.history[0]['content'] == 'Explain lists'
    assert len(context.history) == 2
engine.dispose()
"""
    environment = dict(os.environ, TEST_CHAT_SCHEMA=schema, TEST_CHAT_USER=str(owner), TEST_CHAT_CONVERSATION=conversation_id)
    result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                            env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_failed_run_resumes_without_repeating_retrieval(chat):
    client, _, retrieval, agent = chat
    request_id = str(uuid4())
    agent.side_effect = RuntimeError('temporary outage')
    failed = client.post('/query', json={'query': 'Explain lists', 'request_id': request_id})
    assert failed.status_code == 503
    assert failed.json()['detail']['request_id'] == request_id
    assert len(retrieval) == 1
    agent.side_effect = None
    resumed = client.post(f'/chat-runs/{request_id}/resume')
    assert resumed.status_code == 200
    assert resumed.json()['request_id'] == request_id
    assert len(retrieval) == 1
    conversation_id = resumed.json()['conversation_id']
    calls = agent.call_count
    repeated = client.post(f'/chat-runs/{request_id}/resume')
    assert repeated.json() == resumed.json()
    assert agent.call_count == calls
    assert len(client.get(f'/conversations/{conversation_id}/messages').json()) == 2
    assert client.post('/query', json={'query': 'Different question', 'request_id': request_id}).status_code == 409
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    assert client.post(f'/chat-runs/{request_id}/resume').status_code == 404


def test_graph_resumes_after_process_restart(chat):
    import os
    import subprocess
    import sys
    from pathlib import Path
    client, owner, retrieval, agent = chat
    request_id = str(uuid4())
    agent.side_effect = RuntimeError('interrupted provider call')
    assert client.post('/query', json={'query': 'Explain lists', 'request_id': request_id}).status_code == 503
    assert len(retrieval) == 1
    database = app.dependency_overrides[get_db]()
    db = next(database)
    schema = db.get_bind().get_execution_options()['schema_translate_map'][None]
    database.close()
    code = """
import os
from uuid import UUID
from unittest.mock import AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.ai import graph
from app.services import chat_service
from app.schemas.chat import TutorAnswer
url = make_url(get_settings().database_url).set(drivername='postgresql').update_query_dict({'options': '-csearch_path=' + os.environ['TEST_CHAT_SCHEMA']}).render_as_string(hide_password=False)
graph.get_checkpoint_uri = lambda: url
def forbidden(*args, **kwargs):
    raise AssertionError('Retrieval was repeated after restart')
chat_service.get_document_embeddings = forbidden
chat_service.generate_reply = AsyncMock(return_value=TutorAnswer(status='answered', answer='Restored explanation', citation_ids=[1]))
engine = create_engine(get_settings().database_url).execution_options(schema_translate_map={None: os.environ['TEST_CHAT_SCHEMA']})
with Session(engine, expire_on_commit=False) as db:
    response = chat_service.execute_run(db, UUID(os.environ['TEST_CHAT_USER']), UUID(os.environ['TEST_CHAT_REQUEST']), None, None)
    assert response.answer == 'Restored explanation'
engine.dispose()
"""
    env = dict(os.environ, TEST_CHAT_SCHEMA=schema, TEST_CHAT_USER=str(owner), TEST_CHAT_REQUEST=request_id)
    result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    conversations = client.get('/conversations').json()
    assert len(conversations) == 1
    messages = client.get('/conversations/' + conversations[0]['id'] + '/messages').json()
    assert len(messages) == 2 and messages[1]['content'] == 'Restored explanation'


def test_summary_preferences_and_optional_evidence(chat):
    client, _, _, model = chat
    response = client.post('/query',json={'query':'Summarize the list concept','action':'summarize'})
    assert response.status_code == 200, response.text
    assert model.call_args.kwargs['action'] == 'summarize'
    assert model.call_args.kwargs['preferences']['detail'] == 'balanced'
    evidence = client.get('/chat-runs/' + response.json()['request_id'] + '/evidence')
    assert evidence.status_code == 200 and evidence.json()[0]['page'] == 2
    assert evidence.json()[0]['page_url'].endswith('?page=2')
    assert 'sources' not in response.json()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    assert client.get('/chat-runs/' + response.json()['request_id'] + '/evidence').status_code == 404


def test_quiz_action_is_saved_and_replay_safe(chat,monkeypatch):
    from app.services import quiz_service
    from app.schemas.quiz import GeneratedQuiz
    from test_quizzes import generated
    client = chat[0]
    monkeypatch.setattr(quiz_service,'get_document_embeddings',chat_service.get_document_embeddings)
    generator = AsyncMock(return_value=GeneratedQuiz.model_validate(generated()))
    monkeypatch.setattr(quiz_service,'generate_quiz',generator)
    request_id = str(uuid4())
    result = client.post('/query',json={'query':'Quiz me on lists','request_id':request_id})
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'quiz_ready'
    assert len(result.json()['quiz']['questions']) == 5
    repeated = client.post('/chat-runs/' + request_id + '/resume')
    assert repeated.json() == result.json()
    assert generator.call_count == 1
    assert len(client.get('/quizzes').json()) == 1


@pytest.mark.parametrize('query,expected',[
    ('Can you quiz me on promises?','quiz'),
    ('Please generate five practice questions','quiz'),
    ('Could you summarize my notes?','summarize'),
    ('Explain how to generate a quiz','answer'),
    ('What is quiz scoring?','answer'),
    ('Give me an example','answer'),
])
def test_action_routing_rules(query,expected):
    assert chat_service.route_node({'query':query,'requested_action':'auto'})['action'] == expected
