from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from app.core.config import get_settings
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
def client():
    user_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    try:
        with TestClient(app) as client:
            yield client, user_id
    finally:
        app.dependency_overrides.pop(get_current_user, None)


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
    monkeypatch.setattr(document_service, 'get_settings', lambda: SimpleNamespace(max_upload_bytes=5))
    assert client[0].post('/documents/upload', files={'file': ('a.pdf', b'%PDF-too-large', 'application/pdf')}).status_code == 413
    monkeypatch.setattr(document_service, 'get_settings', get_settings)
    def fail(*args, **kwargs):
        raise RuntimeError('private provider details')
    monkeypatch.setattr(document_service, 'create_document_embeddings', fail)
    response = client[0].post('/documents/upload', files={'file': ('a.pdf', make_pdf(), 'application/pdf')})
    assert response.status_code == 503
    assert 'private provider details' not in response.text


def test_upload_requires_authentication():
    with TestClient(app) as client:
        assert client.post('/documents/upload', files={'file': ('a.pdf', make_pdf(), 'application/pdf')}).status_code == 401
