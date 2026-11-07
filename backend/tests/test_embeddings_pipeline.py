import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from app.ai import rag
from app.ai import vectorstore


class FakeEmbeddings(Embeddings):
    """Deterministic test vectors; no downloaded model or API calls."""

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        return [float('python' in text.lower()), float('history' in text.lower()), 0.1]


def test_upload_then_chat_with_user_isolation(monkeypatch):
    client = QdrantClient(':memory:')
    client.create_collection('test', vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE))
    store = QdrantVectorStore(client=client, collection_name='test', embedding=FakeEmbeddings())
    real_close = client.close
    monkeypatch.setattr(client, 'close', lambda: None)
    monkeypatch.setattr(rag, 'add_documents', lambda docs, ids: store.add_documents(docs, ids=ids))
    monkeypatch.setattr(rag, 'get_vector_store', lambda: store)
    try:
        original = Document(page_content='Python study notes', metadata={'page': 2, 'document_id': 'pdf-1'})
        ids = rag.create_document_embeddings([original], user_id='alice')
        assert len(ids) == 1
        assert original.metadata == {'page': 2, 'document_id': 'pdf-1'}
        rag.create_document_embeddings([Document(page_content='Private Python notes')], user_id='bob')
        found = rag.get_document_embeddings('Python', user_id='alice')
        assert len(found) == 1
        assert found[0].page_content == original.page_content
        assert found[0].metadata['page'] == 2
        assert rag.get_document_embeddings('Python', user_id='unknown') == []
    finally:
        real_close()


def test_invalid_input_does_not_access_qdrant(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Invalid input reached Qdrant')
    monkeypatch.setattr(rag, 'add_documents', unexpected)
    monkeypatch.setattr(rag, 'get_vector_store', unexpected)
    for docs in [[], [Document(page_content=' ')], ['not a Document']]:
        with pytest.raises(ValueError):
            rag.create_document_embeddings(docs, user_id='alice')
    for query, k in [(' ', 4), ('python', 0), ('python', 21)]:
        with pytest.raises(ValueError):
            rag.get_document_embeddings(query, user_id='alice', k=k)


def test_stable_chunk_ids_and_ready_document_filter(monkeypatch):
    saved=[]
    monkeypatch.setattr(rag,'add_documents',lambda docs,ids:saved.append(ids))
    docs=[Document(page_content='Python notes',metadata={'document_id':'doc-1','chunk_index':0})]
    first=rag.create_document_embeddings(docs,user_id='alice')
    second=rag.create_document_embeddings(docs,user_id='alice')
    assert first == second
    assert rag.get_document_embeddings('Python',user_id='alice',document_ids=[]) == []


def test_chat_drops_chunks_from_unready_documents(monkeypatch):
    from app.services import chat_service
    monkeypatch.setattr(chat_service,'get_document_embeddings',lambda *args,**kwargs:[Document(page_content='Partial upload',metadata={'document_id':'processing-id'})])
    result=chat_service.retrieve_node({'history':[],'query':'Explain','user_id':'alice','ready_document_ids':['ready-id']})
    assert result['passages'] == []


def test_fixed_evaluation_fixture_is_complete():
    from pathlib import Path
    import json
    fixture=json.loads((Path(__file__).resolve().parents[1]/'evaluation'/'cases.json').read_text())
    assert len(fixture['questions']) == 20
    pages={(item['document'],item['page']) for item in fixture['corpus']}
    assert all((case['expected_document'],case['expected_page']) in pages for case in fixture['questions'] if case['expected_document'])
    assert sum(case['expected_document'] is None for case in fixture['questions']) == 4


def test_retry_cleanup_with_real_qdrant_client_preserves_other_documents(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4
    client = QdrantClient(':memory:')
    client.create_collection('retry-test', vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE))
    client.upsert('retry-test', points=[models.PointStruct(id=str(uuid4()), vector=[1., 0., .1], payload={'metadata': {'user_id': user, 'document_id': document}})
        for user, document in [('alice','doc-1'), ('alice','doc-2'), ('bob','doc-1')]])
    real_close = client.close
    closed = []
    monkeypatch.setattr(client, 'close', lambda: closed.append(True))
    monkeypatch.setattr(vectorstore, 'QdrantClient', lambda **kwargs: client)
    monkeypatch.setattr(vectorstore, 'get_settings', lambda: SimpleNamespace(qdrant_url='unused', qdrant_collection_name='retry-test'))
    try:
        vectorstore.delete_document_vectors('doc-1', 'alice')
        points, _ = client.scroll('retry-test', limit=10)
        remaining = {(point.payload['metadata']['user_id'], point.payload['metadata']['document_id']) for point in points}
        assert remaining == {('alice','doc-2'), ('bob','doc-1')}
        assert closed == [True]
        def unavailable(*args): raise RuntimeError('Qdrant unavailable')
        monkeypatch.setattr(client, 'collection_exists', unavailable)
        with pytest.raises(RuntimeError, match='Qdrant unavailable'):
            vectorstore.delete_document_vectors('doc-1', 'alice')
        assert closed == [True, True]
    finally:
        real_close()
