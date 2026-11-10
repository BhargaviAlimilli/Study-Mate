"""Deployment configuration checks do not provision resources or call paid APIs."""
import importlib.util
import os
from pathlib import Path
import sys
from unittest.mock import Mock
import pytest
from sqlalchemy.engine import make_url
from app.core.container import configure_container_database
from app import start

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('prepare_demo_env', ROOT / 'deploy/free/prepare_env.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def test_prepare_env_generates_secrets_and_refuses_overwrite(tmp_path):
    target = tmp_path / '.env'
    prepare.write_env('my-demo.duckdns.org', 'synthetic-key-$literal', target)
    assert prepare.check_env(target) == 'my-demo.duckdns.org'
    original = target.read_text()
    assert "ALLOW_REGISTRATION='false'" in original
    assert "ANTHROPIC_API_KEY='synthetic-key-$literal'" in original
    with pytest.raises(FileExistsError):
        prepare.write_env('my-demo.duckdns.org', 'a-different-key', target)
    assert target.read_text() == original
    if os.name != 'nt':
        assert target.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('host', ['https://my-demo.duckdns.org', 'localhost', '127.0.0.1', 'my-demo.duckdns.org/path', 'your-unique-name.duckdns.org'])
def test_public_host_validation(host):
    with pytest.raises(ValueError):
        prepare.validate_host(host)


def test_container_database_preserves_special_password_characters(monkeypatch):
    for name, value in {'POSTGRES_SERVICE_HOST':'postgres','POSTGRES_USER':'learner','POSTGRES_PASSWORD':'synthetic:@/#password','POSTGRES_DB':'study'}.items():
        monkeypatch.setenv(name,value)
    monkeypatch.setenv('DATABASE_URL','unused')
    configure_container_database()
    url = make_url(os.environ['DATABASE_URL'])
    assert url.host == 'postgres' and url.password == 'synthetic:@/#password'
    assert url.database == 'study' and url.port == 5432


@pytest.mark.parametrize('mode,expected_calls,serves', [('--migrate-only',2,False),('--serve-only',0,True),(None,2,True)])
def test_migration_and_serve_modes(monkeypatch,mode,expected_calls,serves):
    monkeypatch.setattr(sys,'argv',['app.start'] + ([mode] if mode else []))
    monkeypatch.setattr(start,'configure_container_database',lambda:None)
    run, execute = Mock(), Mock()
    monkeypatch.setattr(start.subprocess,'run',run)
    monkeypatch.setattr(start.os,'execvp',execute)
    monkeypatch.setenv('FORWARDED_ALLOW_IPS','172.29.0.0/24')
    monkeypatch.setenv('PORT','8000')
    start.main()
    assert run.call_count == expected_calls
    assert execute.called == serves
    if serves:
        assert execute.call_args.args[1][-1] == '172.29.0.0/24'
