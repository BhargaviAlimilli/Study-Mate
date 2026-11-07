"""Exercise the actual Redis/RQ transport without touching application queue jobs."""
import os
from uuid import uuid4
import pytest
from redis import Redis
from redis.exceptions import RedisError
from rq import Queue, SimpleWorker
from rq.timeouts import TimerDeathPenalty
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings
from app.core.database import get_db
from app.main import app
from app.services import document_service
from app.workers import document_worker
from test_documents import client, make_pdf


def test_real_redis_worker_transitions_and_duplicate_protection(client, monkeypatch):
    redis = Redis.from_url(get_settings().redis_url, socket_connect_timeout=3, socket_timeout=3)
    try:
        redis.ping()
    except RedisError:
        if os.environ.get('REQUIRE_REDIS_TESTS') == '1':
            pytest.fail('Redis is required for the configured CI ingestion check')
        pytest.skip('Start Redis to run the real broker/worker integration test')
    queue = Queue('test-ingestion-' + uuid4().hex, connection=redis)
    monkeypatch.setattr(document_worker, 'ingestion_queue', lambda: queue)
    monkeypatch.setattr(get_settings(), 'background_ingestion', True)
    calls = []
    monkeypatch.setattr(document_service, 'create_document_embeddings', lambda docs, **kw: calls.append(docs) or ['chunk-id'])
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    monkeypatch.setattr(document_worker, 'SessionLocal', sessionmaker(db.get_bind(), expire_on_commit=False))
    jobs = []
    try:
        http, owner = client
        content = make_pdf()
        upload = http.post('/documents/upload', files={'file':('notes.pdf',content,'application/pdf')})
        assert upload.status_code == 202
        jobs = queue.get_jobs()
        assert len(jobs) == 1 and calls == []
        assert all(isinstance(arg,str) for arg in jobs[0].args)
        assert http.get('/documents').json()[0]['status'] == 'queued'
        assert http.post('/documents/upload', files={'file':('duplicate.pdf',content,'application/pdf')}).status_code == 202
        assert queue.count == 1
        class PortableWorker(SimpleWorker):
            death_penalty_class = TimerDeathPenalty
        worker = PortableWorker([queue],connection=redis,name='test-worker-'+uuid4().hex)
        worker.work(burst=True,logging_level='ERROR')
        jobs[0].refresh()
        assert jobs[0].is_finished
        assert http.get('/documents').json()[0]['status'] == 'ready'
        assert len(calls) == 1
        assert http.post('/documents/upload', files={'file':('duplicate.pdf',content,'application/pdf')}).status_code == 201
        assert queue.count == 0 and len(calls) == 1
    finally:
        for job in jobs:
            job.delete()
        queue.delete(delete_jobs=True)
        generator.close()
        redis.close()
