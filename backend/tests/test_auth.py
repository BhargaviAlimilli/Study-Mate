from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.security import password_hasher
from app.main import app
from app.models.user import AuthSession, User


@pytest.fixture
def auth_client():
    # Each test gets a separate PostgreSQL schema; application rows are untouched.
    schema = "test_auth_" + uuid4().hex
    engine = create_engine(get_settings().database_url)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(test_engine)

    def test_db():
        with Session(test_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = test_db
    try:
        with TestClient(app) as client:
            yield client, test_engine
    finally:
        app.dependency_overrides.pop(get_db, None)
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def register(client):
    return client.post('/auth/register', json={
        'name': '  Alex  ', 'email': 'Alex@Example.com', 'password': 'CorrectHorse123!'
    })


def login(client):
    return client.post('/auth/login', json={
        'email': 'alex@example.com', 'password': 'CorrectHorse123!'
    })


def test_shared_demo_can_disable_public_registration(auth_client, monkeypatch):
    client, engine = auth_client
    monkeypatch.setattr(get_settings(), 'allow_registration', False)
    response = register(client)
    assert response.status_code == 403
    assert 'Public registration is disabled' in response.json()['detail']
    with Session(engine) as db:
        assert db.scalar(select(User)) is None


def test_register_and_validation(auth_client):
    client, engine = auth_client
    response = register(client)
    assert response.status_code == 201
    assert response.json()['name'] == 'Alex'
    assert response.json()['email'] == 'alex@example.com'
    assert 'password' not in response.text
    with Session(engine) as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith('$argon2id$')
        assert password_hasher.verify('CorrectHorse123!', user.password_hash)
        assert user.password_hash != 'CorrectHorse123!'
    assert register(client).status_code == 409
    for payload in [
        {'name': 'Alex', 'email': 'bad-email', 'password': 'ValidPassword123'},
        {'name': '   ', 'email': 'other@example.com', 'password': 'ValidPassword123'},
        {'name': 'Alex', 'email': 'other@example.com', 'password': 'short'},
        {'name': 'Alex', 'email': 'other@example.com'},
        {'name': 'Alex', 'email': 'other@example.com', 'password': 'ValidPassword123', 'role': 'admin'},
    ]:
        response = client.post('/auth/register', json=payload)
        assert response.status_code == 422
        assert '"input"' not in response.text


def test_login_me_logout_and_independent_sessions(auth_client):
    client, engine = auth_client
    register(client)
    response = login(client)
    assert response.status_code == 200
    assert response.json()['expires_in'] == get_settings().access_token_expire_minutes * 60
    assert response.headers['cache-control'] == 'no-store'
    token = response.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    assert client.get('/auth/me', headers=headers).json()['email'] == 'alex@example.com'
    second_token = login(client).json()['access_token']
    assert client.post('/auth/logout', headers=headers).status_code == 200
    assert client.get('/auth/me', headers=headers).status_code == 401
    assert client.post('/auth/logout', headers=headers).status_code == 401
    assert client.get('/auth/me', headers={'Authorization': f'Bearer {second_token}'}).status_code == 200
    with Session(engine) as db:
        assert len(db.scalars(select(AuthSession).where(AuthSession.revoked_at.is_not(None))).all()) == 1


def test_invalid_credentials_and_tokens(auth_client):
    client, engine = auth_client
    register(client)
    for email in ['alex@example.com', 'unknown@example.com']:
        assert client.post('/auth/login', json={
            'email': email, 'password': 'WrongPassword123'
        }).status_code == 401
    assert client.get('/auth/me').status_code == 401
    assert client.post('/auth/logout').status_code == 401
    token = login(client).json()['access_token']
    secret = get_settings().jwt_secret_key.get_secret_value()
    payload = jwt.decode(token, secret, algorithms=['HS256'])
    expired = dict(payload, exp=datetime.now(timezone.utc) - timedelta(seconds=10))
    missing_exp = {key: value for key, value in payload.items() if key != 'exp'}
    unknown_session = dict(payload, jti=str(uuid4()))
    tokens = [
        'invalid', jwt.encode(payload, 'x' * 64, algorithm='HS256'),
        jwt.encode(expired, secret, algorithm='HS256'),
        jwt.encode(missing_exp, secret, algorithm='HS256'),
        jwt.encode(unknown_session, secret, algorithm='HS256'),
    ]
    for bad_token in tokens:
        assert client.get('/auth/me', headers={
            'Authorization': f'Bearer {bad_token}'
        }).status_code == 401
