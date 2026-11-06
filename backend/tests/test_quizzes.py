from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.main import app
from app.models.user import User
from app.models.document import DocumentRecord
from app.models.quiz import Quiz, QuizQuestion
from app.schemas.quiz import GeneratedQuiz
from app.services import quiz_service


def generated():
    return {"status": "ready", "questions": [
        {"question": f"Question about concept {i}?", "options": ["A", "B", "C", "D"],
         "correct_index": i % 4, "explanation": "Internal answer explanation.",
         "topic": f"Concept {i}", "citation_ids": [1]}
        for i in range(5)
    ]}


@pytest.fixture
def quiz_client(monkeypatch):
    schema = "test_quiz_" + uuid4().hex
    engine = create_engine(get_settings().database_url)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(test_engine)
    owner, document_id = uuid4(), uuid4()
    with Session(test_engine) as db:
        db.add(User(id=owner, name="Quiz tester", email="quiz@example.com", password_hash="test-only"))
        db.flush()
        db.add(DocumentRecord(id=document_id, user_id=owner, filename="notes.pdf", pdf_content=b"test",
                              size_bytes=4, page_count=2, chunks_stored=1, status="ready"))
        db.commit()
    def test_db():
        with Session(test_engine, expire_on_commit=False) as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=owner)
    searches = []
    def retrieve(query, **kwargs):
        searches.append(kwargs)
        return [Document(page_content="Study material for five concepts.", metadata={
            "document_id": str(document_id), "page": 1
        })]
    monkeypatch.setattr(quiz_service, "get_document_embeddings", retrieve)
    model = AsyncMock(return_value=GeneratedQuiz.model_validate(generated()))
    monkeypatch.setattr(quiz_service, "generate_quiz", model)
    try:
        with TestClient(app) as client:
            yield client, owner, document_id, test_engine, searches, model, schema
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_generate_persist_and_hide_answers(quiz_client):
    client, owner, doc_id, engine, searches, model, _ = quiz_client
    response = client.post('/quizzes', json={'topic': 'Promises', 'document_id': str(doc_id)})
    assert response.status_code == 201
    body = response.json()
    assert len(body['questions']) == body['question_count'] == 5
    assert [q['position'] for q in body['questions']] == [1, 2, 3, 4, 5]
    for question in body['questions']:
        assert set(question) == {'id', 'position', 'question', 'options'}
    assert 'Internal answer explanation' not in response.text
    assert searches[0]['user_id'] == str(owner) and searches[0]['document_id'] == str(doc_id)
    with Session(engine) as db:
        questions = list(db.scalars(select(QuizQuestion).order_by(QuizQuestion.position)))
        assert len(questions) == 5
        assert questions[0].correct_index == 0
        assert questions[0].explanation == 'Internal answer explanation.'
        assert questions[0].evidence[0]['document_id'] == str(doc_id)
    assert client.get('/quizzes/' + body['id']).json() == body
    assert client.get('/quizzes').json()[0]['id'] == body['id']
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    assert client.get('/quizzes').json() == []
    assert client.get('/quizzes/' + body['id']).status_code == 404
    assert client.post('/quizzes', json={'topic': 'Promises', 'document_id': str(doc_id)}).status_code == 404
    assert model.call_count == 1


@pytest.mark.parametrize('payload', [{}, {'topic': ' '}, {'topic': 'x' * 201}, {'topic': 'Python', 'question_count': 3}, {'topic': 'Python', 'user_id': 'other'}])
def test_request_validation(quiz_client, payload):
    assert quiz_client[0].post('/quizzes', json=payload).status_code == 422
    quiz_client[5].assert_not_called()


@pytest.mark.parametrize('defect', ['count', 'duplicate_options', 'wrong_index', 'duplicate_question', 'unknown_source'])
def test_invalid_generation_not_saved(quiz_client, defect):
    client, _, _, engine, _, model, _ = quiz_client
    output = generated()
    if defect == 'count':
        output['questions'].pop()
    elif defect == 'duplicate_options':
        output['questions'][0]['options'] = ['A', ' A ', 'C', 'D']
    elif defect == 'wrong_index':
        output['questions'][0]['correct_index'] = 7
    elif defect == 'duplicate_question':
        output['questions'][1]['question'] = output['questions'][0]['question']
    else:
        output['questions'][0]['citation_ids'] = [99]
    model.return_value = output
    assert client.post('/quizzes', json={'topic': 'Promises'}).status_code == 502
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Quiz)) == 0
        assert db.scalar(select(func.count()).select_from(QuizQuestion)) == 0


def test_insufficient_material_and_errors(quiz_client, monkeypatch):
    client, _, _, _, _, model, _ = quiz_client
    model.return_value = GeneratedQuiz(status='insufficient_context', questions=[])
    assert client.post('/quizzes', json={'topic': 'Unknown topic'}).status_code == 422
    model.side_effect = TimeoutError()
    assert client.post('/quizzes', json={'topic': 'Promises'}).status_code == 504
    model.side_effect = RuntimeError('provider secrets')
    response = client.post('/quizzes', json={'topic': 'Promises'})
    assert response.status_code == 502 and 'provider secrets' not in response.text
    model.reset_mock()
    monkeypatch.setattr(quiz_service, 'get_document_embeddings', lambda *args, **kwargs: [])
    assert client.post('/quizzes', json={'topic': 'Promises'}).status_code == 422
    model.assert_not_called()


def test_quiz_survives_fresh_process(quiz_client):
    import os
    import subprocess
    import sys
    from pathlib import Path
    client, owner, _, _, _, _, schema = quiz_client
    quiz_id = client.post('/quizzes', json={'topic': 'Promises'}).json()['id']
    code = """
import os
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.services.quiz_service import get_owned_quiz
from app.schemas.quiz import QuizResponse
engine = create_engine(get_settings().database_url).execution_options(schema_translate_map={None: os.environ['TEST_SCHEMA']})
with Session(engine) as db:
    quiz = get_owned_quiz(UUID(os.environ['TEST_QUIZ']), UUID(os.environ['TEST_USER']), db)
    public = QuizResponse.model_validate(quiz)
    assert len(public.questions) == 5
    assert 'correct_index' not in public.model_dump_json()
engine.dispose()
"""
    env = dict(os.environ, TEST_SCHEMA=schema, TEST_USER=str(owner), TEST_QUIZ=quiz_id)
    result = subprocess.run([sys.executable, '-c', code], env=env, cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_quiz_requires_authentication():
    with TestClient(app) as client:
        assert client.post('/quizzes', json={'topic': 'Promises'}).status_code == 401
        assert client.get('/quizzes').status_code == 401
