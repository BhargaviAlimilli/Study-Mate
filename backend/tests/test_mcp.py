"""Real MCP client/transport and JWT verification against isolated PostgreSQL data."""
import asyncio
from datetime import datetime, timezone
from uuid import uuid4
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.orm import sessionmaker, Session
from langchain_core.documents import Document
from app.ai import tools
from app.models.document import DocumentRecord
from app.models.quiz import Quiz, QuizAttempt
from app.models.progress import RevisionItem
from test_auth import auth_client, register, login


def test_real_mcp_client_tools_ownership_and_revocation(auth_client, monkeypatch):
    http, engine = auth_client
    register(http)
    first = login(http).json()['access_token']
    second_user = http.post('/auth/register', json={'name':'Other', 'email':'other@example.com', 'password':'CorrectHorse123!'}).json()
    second = http.post('/auth/login', json={'email':'other@example.com', 'password':'CorrectHorse123!'}).json()['access_token']
    first_user = http.get('/auth/me', headers={'Authorization':f'Bearer {first}'}).json()
    from uuid import UUID
    owner = UUID(first_user['id'])
    other = UUID(second_user['id'])
    document_id = uuid4()
    with Session(engine) as db:
        db.add(DocumentRecord(id=document_id,user_id=owner,filename='private.pdf',pdf_content=b'test',size_bytes=4,page_count=1,chunks_stored=1,status='ready'))
        quiz = Quiz(user_id=owner,topic='Lists',question_count=5)
        db.add(quiz); db.flush()
        attempt = QuizAttempt(quiz_id=quiz.id,user_id=owner,submission_id=uuid4(),score=0,total=5)
        db.add(attempt); db.flush()
        db.add(RevisionItem(user_id=owner,topic='Private lists',topic_key='private lists',status='pending',attempt_id=attempt.id,evidence=[],missed_question_ids=[str(uuid4())],last_missed_at=datetime.now(timezone.utc)))
        db.commit()
    monkeypatch.setattr(tools, 'SessionLocal', sessionmaker(engine,expire_on_commit=False))
    def search(query, **kwargs):
        assert kwargs['user_id'] == str(owner)
        assert kwargs['document_ids'] == [str(document_id)]
        return [Document(page_content='Private list notes',metadata={'document_id':str(document_id),'page':1})]
    monkeypatch.setattr(tools,'get_document_embeddings',search)

    async def verify():
        server, application = tools.create_mcp_app()
        import socket
        import uvicorn
        from fastapi import FastAPI
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def lifespan(app):
            async with server.session_manager.run():
                yield
        wrapper = FastAPI(lifespan=lifespan)
        wrapper.mount('/', application)
        listener = socket.socket(); listener.bind(('127.0.0.1', 0))
        endpoint = f'http://127.0.0.1:{listener.getsockname()[1]}/mcp'
        running = uvicorn.Server(uvicorn.Config(wrapper, log_level='error'))
        task = asyncio.create_task(running.serve(sockets=[listener]))
        try:
            for _ in range(500):
                if running.started: break
                if task.done(): await task
                await asyncio.sleep(.01)
            assert running.started, 'MCP test server did not start'
            async def read(token):
                async with httpx2.AsyncClient(timeout=10,headers={'Authorization':f'Bearer {token}'}) as client:
                    async with streamable_http_client(endpoint,http_client=client) as streams:
                        async with ClientSession(streams[0],streams[1]) as session:
                            await session.initialize()
                            listed = await session.list_tools()
                            assert {t.name for t in listed.tools} == {'search_notes','get_weak_topics'}
                            notes = await session.call_tool('search_notes', {'query':'lists'})
                            weak = await session.call_tool('get_weak_topics', {})
                            assert not notes.is_error and not weak.is_error
                            return notes.model_dump_json(), weak.model_dump_json()
            notes, weak = await read(first)
            assert 'Private list notes' in notes and 'Private lists' in weak
            notes, weak = await read(second)
            assert 'Private list notes' not in notes and 'Private lists' not in weak
            async with httpx2.AsyncClient(timeout=10) as client:
                body = {'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}}
                headers = {'accept':'application/json, text/event-stream'}
                assert (await client.post(endpoint,json=body,headers=headers)).status_code == 401
                assert (await client.post(endpoint,json=body,headers={**headers,'Authorization':'Bearer invalid'})).status_code == 401
                assert http.post('/auth/logout',headers={'Authorization':f'Bearer {first}'}).status_code == 200
                assert (await client.post(endpoint,json=body,headers={**headers,'Authorization':f'Bearer {first}'})).status_code == 401
        finally:
            running.should_exit = True
            await asyncio.wait_for(task, 10)
            listener.close()
    asyncio.run(asyncio.wait_for(verify(), 45))
