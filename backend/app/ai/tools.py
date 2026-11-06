"""Authenticated read-only MCP tools; clients supply the app's bearer token."""
from uuid import UUID
from fastapi.security import HTTPAuthorizationCredentials
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from mcp.server.mcpserver import MCPServer
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp_types import ToolAnnotations
from app.core.database import SessionLocal
from app.core.security import get_current_session
from app.models.user import User
from app.models.document import DocumentRecord
from app.models.progress import RevisionItem
from app.ai.rag import get_document_embeddings
from app.services.progress_service import revision_response
from app.core.config import get_settings


def validate_token(token: str):
    with SessionLocal() as db:
        session = get_current_session(HTTPAuthorizationCredentials(scheme='Bearer', credentials=token), db)
        if db.get(User, session.user_id) is None:
            raise HTTPException(401, 'Invalid user')
        return str(session.user_id), int(session.expires_at.timestamp())


class JWTVerifier:
    async def verify_token(self, token: str):
        try:
            user_id, expiry = await run_in_threadpool(validate_token, token)
            return AccessToken(token=token, client_id=user_id, subject=user_id, scopes=['notes:read'],
                expires_at=expiry, resource=get_settings().api_public_url.rstrip('/') + '/mcp')
        except Exception:
            return None


readonly = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def tool_user() -> UUID:
    token = get_access_token()
    if token is None:
        raise ValueError('Authentication required.')
    return UUID(token.client_id)


def search_for_user(user_id, query, k):
    with SessionLocal() as db:
        ids = [str(value) for value in db.scalars(select(DocumentRecord.id).where(
            DocumentRecord.user_id == user_id, DocumentRecord.status == 'ready'))]
    if not ids:
        return []
    from app.ai.vectorstore import MissingCollectionError
    try:
        docs = get_document_embeddings(query, user_id=str(user_id), k=k, document_ids=ids)
    except MissingCollectionError:
        return []
    return [{'text': doc.page_content, 'metadata': doc.metadata} for doc in docs]


async def search_notes(query: str, k: int = 4) -> list[dict]:
    """Search the authenticated user's ready study notes. Never reads other users' notes."""
    if not query.strip() or len(query) > 4000 or not 1 <= k <= 10:
        raise ValueError('Provide a query of 1-4000 characters and k between 1 and 10.')
    try:
        return await run_in_threadpool(search_for_user, tool_user(), query.strip(), k)
    except Exception as exc:
        raise ValueError('Study note search is unavailable.') from None


def weak_for_user(user_id):
    with SessionLocal() as db:
        return [revision_response(item).model_dump(mode='json') for item in db.scalars(
            select(RevisionItem).where(RevisionItem.user_id == user_id, RevisionItem.status == 'pending')
            .order_by(RevisionItem.last_missed_at.desc()).limit(100))]


async def get_weak_topics() -> list[dict]:
    """Return pending revision topics linked to this user's quiz attempts and PDF pages."""
    try:
        return await run_in_threadpool(weak_for_user, tool_user())
    except Exception:
        raise ValueError('Revision topics are unavailable.') from None


def create_mcp_app():
    server = MCPServer('Study Mate read-only tools', token_verifier=JWTVerifier(), auth=AuthSettings(
    issuer_url=get_settings().api_public_url,
    resource_server_url=get_settings().api_public_url.rstrip('/') + '/mcp',
    required_scopes=['notes:read'], validate_token_resource=True))
    server.tool(annotations=readonly)(search_notes)
    server.tool(annotations=readonly)(get_weak_topics)
    from urllib.parse import urlparse
    return server, server.streamable_http_app(stateless_http=True, json_response=True,
        host=urlparse(get_settings().api_public_url).hostname or '127.0.0.1')


class MCPMount:
    app = None

    async def __call__(self, scope, receive, send):
        if self.app is None:
            from starlette.responses import JSONResponse
            await JSONResponse({"detail": "MCP service is starting."}, status_code=503)(scope, receive, send)
        else:
            await self.app(scope, receive, send)


mcp_mount = MCPMount()
