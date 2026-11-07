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
from app.models.quiz import Quiz, QuizQuestion, QuizAttempt, QuizAttemptAnswer
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


def saved_quiz(client):
    response = client.post('/quizzes', json={'topic': 'Promises'})
    assert response.status_code == 201
    return response.json()


def submission(quiz, mode='correct'):
    return {'submission_id': str(uuid4()), 'answers': [
        {'question_id': q['id'], 'selected_index': index % 4 if mode == 'correct' else (index + 1) % 4}
        for index, q in enumerate(quiz['questions'])
    ]}


@pytest.mark.parametrize('mode,score', [('correct', 5), ('wrong', 0)])
def test_submit_score_and_save_results(quiz_client, mode, score):
    client, _, _, engine, _, model, _ = quiz_client
    quiz = saved_quiz(client)
    response = client.post(f"/quizzes/{quiz['id']}/submit", json=submission(quiz, mode))
    assert response.status_code == 201
    result = response.json()
    assert (result['score'], result['total'], result['percentage']) == (score, 5, score * 20)
    assert len(result['answers']) == 5
    assert all(a['is_correct'] == (mode == 'correct') for a in result['answers'])
    assert result['answers'][0]['explanation'] == 'Internal answer explanation.'
    assert model.call_count == 1  # Only quiz generation calls the model.
    assert client.get(f"/quizzes/{quiz['id']}/attempts/{result['id']}").json() == result
    assert client.get(f"/quizzes/{quiz['id']}/attempts").json()[0]['id'] == result['id']
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(QuizAttempt)) == 1
        assert db.scalar(select(func.count()).select_from(QuizAttemptAnswer)) == 5
    # The pre-submission quiz API still never includes the answer key.
    assert 'correct_index' not in client.get('/quizzes/' + quiz['id']).text


def test_mixed_score_idempotency_and_ownership(quiz_client):
    client, owner, _, engine, _, _, _ = quiz_client
    quiz = saved_quiz(client)
    payload = submission(quiz)
    payload['answers'][-1]['selected_index'] = 1
    first = client.post(f"/quizzes/{quiz['id']}/submit", json=payload)
    assert first.json()['score'] == 4 and first.json()['percentage'] == 80
    payload['answers'].reverse()
    repeated = client.post(f"/quizzes/{quiz['id']}/submit", json=payload)
    assert repeated.status_code == 200 and repeated.json() == first.json()
    payload['answers'][0]['selected_index'] = 2
    assert client.post(f"/quizzes/{quiz['id']}/submit", json=payload).status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(QuizAttempt)) == 1
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    assert client.post(f"/quizzes/{quiz['id']}/submit", json=payload).status_code == 404
    assert client.get(f"/quizzes/{quiz['id']}/attempts").status_code == 404
    assert client.get(f"/quizzes/{quiz['id']}/attempts/{first.json()['id']}").status_code == 404


@pytest.mark.parametrize('defect', ['missing', 'duplicate', 'unknown', 'negative', 'large', 'bool', 'string', 'float', 'score'])
def test_bad_submissions_are_not_saved(quiz_client, defect):
    client, _, _, engine, _, _, _ = quiz_client
    quiz = saved_quiz(client)
    payload = submission(quiz)
    if defect == 'missing':
        payload['answers'].pop()
    elif defect == 'duplicate':
        payload['answers'][1]['question_id'] = payload['answers'][0]['question_id']
    elif defect == 'unknown':
        payload['answers'][0]['question_id'] = str(uuid4())
    elif defect == 'score':
        payload['score'] = 5
    else:
        payload['answers'][0]['selected_index'] = {'negative': -1, 'large': 4, 'bool': True, 'string': '0', 'float': 0.0}[defect]
    assert client.post(f"/quizzes/{quiz['id']}/submit", json=payload).status_code == 422
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(QuizAttempt)) == 0


def test_attempt_save_is_atomic(quiz_client):
    from sqlalchemy import event
    client, _, _, engine, _, _, _ = quiz_client
    quiz = saved_quiz(client)
    def fail_answers(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('INSERT') and 'quiz_attempt_answers' in statement:
            raise RuntimeError('Simulated database failure')
    event.listen(engine, 'before_cursor_execute', fail_answers)
    try:
        assert client.post(f"/quizzes/{quiz['id']}/submit", json=submission(quiz)).status_code == 503
    finally:
        event.remove(engine, 'before_cursor_execute', fail_answers)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(QuizAttempt)) == 0
        assert db.scalar(select(func.count()).select_from(QuizAttemptAnswer)) == 0


def test_attempt_survives_fresh_process(quiz_client):
    import os
    import subprocess
    import sys
    from pathlib import Path
    client, owner, _, _, _, _, schema = quiz_client
    quiz = saved_quiz(client)
    attempt = client.post(f"/quizzes/{quiz['id']}/submit", json=submission(quiz)).json()
    code = """
import os
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.services.quiz_service import get_owned_attempt
from app.schemas.quiz import AttemptResponse
engine = create_engine(get_settings().database_url).execution_options(schema_translate_map={None: os.environ['TEST_SCHEMA']})
with Session(engine) as db:
    saved = get_owned_attempt(UUID(os.environ['TEST_QUIZ']), UUID(os.environ['TEST_ATTEMPT']), UUID(os.environ['TEST_USER']), db)
    from app.services.feedback_service import build_attempt_response
    result = build_attempt_response(saved)
    assert result.score == 5 and result.percentage == 100
    assert len(result.answers) == 5 and all(a.is_correct for a in result.answers)
    assert len(result.feedback.strengths) == 5 and not result.feedback.needs_review
engine.dispose()
"""
    env = dict(os.environ, TEST_SCHEMA=schema, TEST_USER=str(owner), TEST_QUIZ=quiz['id'], TEST_ATTEMPT=attempt['id'])
    result = subprocess.run([sys.executable, '-c', code], env=env, cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_feedback_groups_strengths_review_and_pdf_pages(quiz_client):
    client, _, document_id, _, _, model, _ = quiz_client
    output = generated()
    topics = ['Promise basics', 'promise basics', 'Microtasks', 'Microtasks', 'Error handling']
    for question, topic in zip(output['questions'], topics):
        question['topic'] = topic
    model.return_value = GeneratedQuiz.model_validate(output)
    quiz = saved_quiz(client)
    payload = submission(quiz)
    payload['answers'][1]['selected_index'] = 0
    payload['answers'][4]['selected_index'] = 1
    response = client.post(f"/quizzes/{quiz['id']}/submit", json=payload)
    assert response.status_code == 201
    result = response.json()
    feedback = result['feedback']
    assert result['score'] == 3
    assert '3 of 5' in feedback['summary']
    assert len(feedback['strengths']) == 1
    assert feedback['strengths'][0]['topic'] == 'Microtasks'
    assert feedback['strengths'][0]['correct'] == feedback['strengths'][0]['total'] == 2
    assert len(feedback['needs_review']) == 2
    basics = feedback['needs_review'][0]
    assert basics['topic'] == 'Promise basics'
    assert (basics['correct'], basics['total']) == (1, 2)
    assert basics['question_ids'] == [quiz['questions'][1]['id']]
    assert len(basics['sources']) == 1
    source = basics['sources'][0]
    assert source == {
        'excerpt': 'Study material for five concepts.',
        'document_id': str(document_id), 'filename': 'notes.pdf', 'page': 1,
        'file_url': f'/documents/{document_id}/file',
        'page_url': f'/documents/{document_id}/file?page=1',
    }
    assert result['answers'][1]['sources'] == basics['sources']
    assert 'not been assessed' in feedback['assessment_note']
    assert client.get(f"/quizzes/{quiz['id']}/attempts/{result['id']}").json()['feedback'] == feedback
    assert source['excerpt'] == 'Study material for five concepts.'
    assert 'citation_ids' not in response.text
    assert model.call_count == 1


@pytest.mark.parametrize('mode,strengths,review', [('correct', 5, 0), ('wrong', 0, 5)])
def test_feedback_all_correct_or_all_wrong(quiz_client, mode, strengths, review):
    client = quiz_client[0]
    quiz = saved_quiz(client)
    feedback = client.post(f"/quizzes/{quiz['id']}/submit", json=submission(quiz, mode)).json()['feedback']
    assert len(feedback['strengths']) == strengths
    assert len(feedback['needs_review']) == review
    assert feedback['next_steps']
    assert 'mastered' not in feedback['summary'].lower()


def test_source_links_skip_malformed_and_deduplicate_pages():
    from app.services.feedback_service import review_sources
    doc_id = str(uuid4())
    valid = {'document_id': doc_id, 'filename': 'notes.pdf', 'page': 2}
    assert len(review_sources([valid, valid])) == 1
    assert review_sources([{}, dict(valid, document_id='not-a-uuid'), dict(valid, page=-1), dict(valid, page=True)]) == []


def test_revision_plan_progress_and_review_lifecycle(quiz_client):
    client = quiz_client[0]
    quiz = saved_quiz(client)
    assert all(topic['status'] == 'not_assessed' for topic in client.get('/progress').json()['topics'])
    first = client.post(f"/quizzes/{quiz['id']}/submit", json=submission(quiz, 'wrong'))
    assert first.status_code == 201
    revisions = client.get('/revisions?status=pending').json()
    assert len(revisions) == 5
    item = revisions[0]
    assert item['sources'][0]['page_url'].endswith('?page=1')
    assert client.patch('/revisions/' + item['id'], json={'status':'reviewed'}).status_code == 200
    assert client.post('/revisions/sync').status_code == 200
    assert len(client.get('/revisions?status=reviewed').json()) == 1
    assert client.post(f"/quizzes/{quiz['id']}/submit", json=submission(quiz, 'wrong')).status_code == 201
    assert len(client.get('/revisions?status=pending').json()) == 5
    assert client.post('/revisions/' + item['id'] + '/quiz').status_code == 201
    assert client.get('/progress/recommendations').json()['recommendations']
    assert client.post(f"/quizzes/{quiz['id']}/submit", json=submission(quiz)).status_code == 201
    report = client.get('/progress').json()
    assert report['attempt_count'] == 3
    assert all(topic['trend'] == 'improving' for topic in report['topics'])
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    assert client.get('/revisions').json() == []
    assert client.patch('/revisions/' + item['id'], json={'status':'reviewed'}).status_code == 404
    assert client.post('/revisions/' + item['id'] + '/quiz').status_code == 404


def test_editable_preferences(quiz_client, monkeypatch):
    from app.ai import llm
    monkeypatch.setattr(llm, 'ensure_provider_available', lambda provider: None)
    client = quiz_client[0]
    data = {'detail':'detailed','comparison_language':'Node.js','model_provider':'anthropic'}
    assert client.put('/preferences', json=data).json() == data
    assert client.get('/preferences').json() == data
    assert client.put('/preferences', json={'detail':'unknown'}).status_code == 422


def test_media_validation_and_mocked_providers(quiz_client, monkeypatch):
    from io import BytesIO
    from PIL import Image
    from app.routes import media
    client = quiz_client[0]
    stream = BytesIO()
    Image.new('RGB',(16,16),color='white').save(stream,format='PNG')
    monkeypatch.setattr(media, 'create_agent', lambda **kwargs: object())
    runner = AsyncMock(return_value=SimpleNamespace(final_output=media.ImageExplanation(status='answered',answer='An educational image explanation.')))
    monkeypatch.setattr(media.Runner, 'run', runner)
    assert client.post('/media/image-query', files={'file':('x.png', b'invalid','image/png')}).status_code == 400
    image = client.post('/media/image-query', files={'file':('x.png',stream.getvalue(),'image/png')})
    assert image.status_code == 200 and image.json()['grounding'] == 'uploaded_image'
    assert client.post('/media/transcribe',files={'file':('x.txt',b'text','text/plain')}).status_code == 415
    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        audio = SimpleNamespace(transcriptions=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(text='Explain promises'))),
                                speech=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(content=b'mp3 test'))))
    monkeypatch.setattr(media, 'speech_client', lambda: FakeClient())
    assert client.post('/media/transcribe',files={'file':('x.wav',b'RIFF test','audio/wav')}).json()['text'] == 'Explain promises'
    speech = client.post('/media/speech',json={'text':'Hello learner'})
    assert speech.status_code == 200 and speech.headers['content-type'] == 'audio/mpeg'
    assert speech.headers['x-audio-generated'] == 'ai'


def test_authenticated_read_only_mcp_tools(quiz_client, monkeypatch):
    from app.ai import tools
    from app.models.user import AuthSession
    from app.core.security import create_access_token
    from datetime import datetime, timedelta, timezone
    client, owner, _, engine, _, _, _ = quiz_client
    session_id = uuid4()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    with Session(engine) as db:
        db.add(AuthSession(id=session_id, user_id=owner, expires_at=expiry))
        db.commit()
    monkeypatch.setattr(tools, 'SessionLocal', lambda: Session(engine,expire_on_commit=False))
    token = create_access_token(owner,session_id,expiry)
    headers = {'Authorization':'Bearer ' + token, 'Accept':'application/json, text/event-stream', 'Host':'127.0.0.1:8000'}
    init = {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'tests','version':'1'}}}
    assert client.post('/mcp',json=init,headers={'Accept':'application/json, text/event-stream'}).status_code == 401
    started = client.post('/mcp',json=init,headers=headers)
    assert started.status_code == 200, started.text
    listed = client.post('/mcp',json={'jsonrpc':'2.0','id':2,'method':'tools/list'},headers=headers)
    assert listed.status_code == 200, listed.text
    assert {tool['name'] for tool in listed.json()['result']['tools']} == {'search_notes','get_weak_topics'}
    called = client.post('/mcp',json={'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'get_weak_topics','arguments':{}}},headers=headers)
    assert called.status_code == 200 and not called.json()['result'].get('isError'), called.text
    with Session(engine) as db:
        db.get(AuthSession,session_id).revoked_at = datetime.now(timezone.utc)
        db.commit()
    assert client.post('/mcp',json=init,headers=headers).status_code == 401
