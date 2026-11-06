from io import BytesIO
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.models.user import User
from app.models.document import DocumentRecord
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import Session
from app.core.security import get_current_user
from app.main import app
from app.services import document_service


def make_pdf(*, text=True, encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    if text:
        font = DictionaryObject({
            NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type1'),
            NameObject('/BaseFont'): NameObject('/Helvetica'),
        })
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})
        })
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 20 200 Td (Python study notes for testing.) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
    if encrypted:
        writer.encrypt('test-password')
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def client(monkeypatch):
    schema = "test_documents_" + uuid4().hex
    engine = create_engine(get_settings().database_url)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(test_engine)
    user_id = uuid4()
    with Session(test_engine) as db:
        db.add(User(id=user_id, name="Test user", email="test@example.com", password_hash="test-only"))
        db.commit()
    def test_db():
        with Session(test_engine, expire_on_commit=False) as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    monkeypatch.setattr(document_service, 'delete_document_vectors', lambda *args: None)
    try:
        with TestClient(app) as client:
            yield client, user_id
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_upload_extracts_chunks_and_waits_for_indexing(client, monkeypatch):
    http, user_id = client
    indexed = []
    def index(docs, *, user_id):
        indexed.append((docs, user_id))
        return [str(uuid4()) for _ in docs]
    monkeypatch.setattr(document_service, 'create_document_embeddings', index)
    response = http.post('/documents/upload', files={'file': ('notes.pdf', make_pdf(), 'application/pdf')})
    assert response.status_code == 201
    assert response.json()['chunks_stored'] == 1
    docs, owner = indexed[0]
    assert owner == str(user_id)
    assert 'Python study notes' in docs[0].page_content
    assert docs[0].metadata['page'] == 1
    assert docs[0].metadata['document_id'] == response.json()['document_id']
    assert docs[0].metadata['filename'] == 'notes.pdf'
    assert 'workspace_id' not in docs[0].metadata


@pytest.mark.parametrize('filename,content,mime,status', [
    ('notes.txt', b'text', 'text/plain', 415),
    ('notes.pdf', b'%PDF-invalid', 'text/plain', 415),
    ('notes.pdf', b'', 'application/pdf', 400),
    ('notes.pdf', b'not a pdf', 'application/pdf', 400),
    ('notes.pdf', b'%PDF-invalid', 'application/pdf', 400),
    ('notes.pdf', make_pdf(text=False), 'application/pdf', 400),
    ('notes.pdf', make_pdf(encrypted=True), 'application/pdf', 400),
])
def test_invalid_upload_is_not_indexed(client, monkeypatch, filename, content, mime, status):
    def unexpected(*args, **kwargs):
        pytest.fail('Invalid document reached indexing')
    monkeypatch.setattr(document_service, 'create_document_embeddings', unexpected)
    response = client[0].post('/documents/upload', files={'file': (filename, content, mime)})
    assert response.status_code == status


def test_size_limit_and_storage_failure(client, monkeypatch):
    original_settings = document_service.get_settings
    monkeypatch.setattr(document_service, 'get_settings', lambda: SimpleNamespace(max_upload_bytes=5))
    assert client[0].post('/documents/upload', files={'file': ('a.pdf', b'%PDF-too-large', 'application/pdf')}).status_code == 413
    monkeypatch.setattr(document_service, 'get_settings', original_settings)
    def fail(*args, **kwargs):
        raise RuntimeError('private provider details')
    monkeypatch.setattr(document_service, 'create_document_embeddings', fail)
    response = client[0].post('/documents/upload', files={'file': ('a.pdf', make_pdf(), 'application/pdf')})
    assert response.status_code == 503
    assert 'private provider details' not in response.text


def test_upload_requires_authentication():
    with TestClient(app) as client:
        assert client.post('/documents/upload', files={'file': ('a.pdf', make_pdf(), 'application/pdf')}).status_code == 401


def test_persist_list_open_and_user_isolation(client, monkeypatch):
    http, owner = client
    monkeypatch.setattr(document_service, 'create_document_embeddings', lambda docs, **kwargs: [str(uuid4()) for _ in docs])
    pdf = make_pdf()
    uploaded = http.post('/documents/upload', files={'file': ('../notes.pdf', pdf, 'application/pdf')})
    assert uploaded.status_code == 201
    document_id = uploaded.json()['document_id']
    # Separate requests use separate sessions: persistence does not rely on memory.
    listed = http.get('/documents').json()
    assert len(listed) == 1 and listed[0]['id'] == document_id
    assert listed[0]['filename'] == 'notes.pdf'
    assert listed[0]['status'] == 'ready' and listed[0]['page_count'] == 1
    assert 'pdf_content' not in listed[0]
    database = app.dependency_overrides[get_db]()
    db = next(database)
    try:
        stored = db.get(DocumentRecord, UUID(document_id))
        assert stored.pdf_content == pdf
    finally:
        database.close()
    assert http.get(f'/documents/{document_id}').status_code == 200
    original = http.get(f'/documents/{document_id}/file')
    assert original.content == pdf
    assert original.headers['cache-control'] == 'no-store'
    page = http.get(f'/documents/{document_id}/file?page=1')
    from pypdf import PdfReader
    assert len(PdfReader(BytesIO(page.content)).pages) == 1
    assert http.get(f'/documents/{document_id}/file?page=2').status_code == 404
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    assert http.get('/documents').json() == []
    assert http.get(f'/documents/{document_id}').status_code == 404
    assert http.get(f'/documents/{document_id}/file').status_code == 404


def test_failed_indexing_marks_document_failed(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('index failure')
    cleaned = []
    monkeypatch.setattr(document_service, 'create_document_embeddings', fail)
    monkeypatch.setattr(document_service, 'delete_document_vectors', lambda *args: cleaned.append(args))
    response = client[0].post('/documents/upload', files={'file': ('notes.pdf', make_pdf(), 'application/pdf')})
    assert response.status_code == 503
    documents = client[0].get('/documents').json()
    assert len(documents) == 1 and documents[0]['status'] == 'failed'
    assert documents[0]['chunks_stored'] == 0
    assert cleaned[0] == (documents[0]['id'], str(client[1]))
    assert client[0].get('/documents/' + documents[0]['id'] + '/file').status_code == 409


def test_duplicate_upload_returns_existing_document(client, monkeypatch):
    calls=[]
    monkeypatch.setattr(document_service,'create_document_embeddings',lambda docs, **kwargs: calls.append(docs) or [str(uuid4()) for _ in docs])
    http=client[0]
    content=make_pdf()
    first=http.post('/documents/upload',files={'file':('notes.pdf',content,'application/pdf')})
    again=http.post('/documents/upload',files={'file':('renamed.pdf',content,'application/pdf')})
    assert first.status_code == again.status_code == 201
    assert first.json()['document_id'] == again.json()['document_id']
    assert len(calls) == 1 and len(http.get('/documents').json()) == 1


def test_failed_upload_can_retry_without_duplicate_record(client,monkeypatch):
    http=client[0]
    def fail(*args,**kwargs): raise RuntimeError('temporary failure')
    monkeypatch.setattr(document_service,'create_document_embeddings',fail)
    assert http.post('/documents/upload',files={'file':('notes.pdf',make_pdf(),'application/pdf')}).status_code == 503
    record=http.get('/documents').json()[0]
    monkeypatch.setattr(document_service,'create_document_embeddings',lambda docs,**kwargs:[str(uuid4()) for _ in docs])
    retried=http.post('/documents/' + record['id'] + '/retry')
    assert retried.status_code == 200 and retried.json()['document_id'] == record['id']
    assert len(http.get('/documents').json()) == 1
    assert http.get('/documents').json()[0]['status'] == 'ready'
