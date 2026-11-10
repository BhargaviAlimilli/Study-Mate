"""Create/check the ignored deployment environment without printing secrets."""
import argparse
from getpass import getpass
import ipaddress
import os
from pathlib import Path
import re
import secrets

HERE = Path(__file__).resolve().parent


def validate_host(value: str) -> str:
    value = value.strip().lower()
    labels = value.split('.')
    if len(value) > 253 or len(labels) < 2 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
        raise ValueError('Use a public DNS hostname only, without https://, port, or path.')
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValueError('Use your free DNS hostname, not a raw IP address.')
    if value.endswith(('.invalid', '.localhost', '.local')) or value == 'your-unique-name.duckdns.org':
        raise ValueError('Set the actual DNS hostname assigned to this demo.')
    return value


def write_env(domain: str, key: str, destination: Path = HERE / '.env') -> Path:
    domain = validate_host(domain)
    key = key.strip()
    if not key or any(char in key for char in "\r\n'\\"):
        raise ValueError('Enter a nonempty single-line Claude API key without quote/backslash characters.')
    values = {
        'PUBLIC_HOST': domain, 'APP_SUBNET': '172.29.0.0/24',
        'POSTGRES_USER': 'study_mate', 'POSTGRES_DB': 'study_mate',
        'POSTGRES_PASSWORD': secrets.token_urlsafe(32), 'JWT_SECRET_KEY': secrets.token_urlsafe(48),
        'ANTHROPIC_API_KEY': key, 'ANTHROPIC_MODEL': 'claude-haiku-5-5',
        'ALLOW_REGISTRATION': 'false', 'ACCESS_TOKEN_EXPIRE_MINUTES': '30',
        'BACKGROUND_INGESTION': 'true', 'INGESTION_TIMEOUT_SECONDS': '900',
        'MAX_UPLOAD_BYTES': '10485760', 'QDRANT_COLLECTION_NAME': 'study_mate',
        'EMBEDDING_MODEL_NAME': 'sentence-transformers/all-MiniLM-L6-v2',
    }
    # Exclusive creation deliberately refuses to rotate an existing database password.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as file:
        file.write('# Private deployment configuration. Never commit or paste this file.\n')
        for name, value in values.items():
            file.write(f"{name}='{value}'\n")
    return destination


def check_env(path: Path = HERE / '.env') -> str:
    values = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        name, separator, value = line.partition('=')
        if not separator:
            raise ValueError('Invalid deployment environment line.')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name.strip()] = value
    domain = validate_host(values.get('PUBLIC_HOST', ''))
    for name in ('POSTGRES_PASSWORD', 'JWT_SECRET_KEY'):
        if len(values.get(name, '')) < 32 or values[name].startswith('GENERATED_'):
            raise ValueError(f'{name} must be generated with prepare_env.py.')
    if not values.get('ANTHROPIC_API_KEY') or values['ANTHROPIC_API_KEY'].startswith('ENTER_'):
        raise ValueError('Set your existing Claude API key locally.')
    network = ipaddress.ip_network(values.get('APP_SUBNET', ''), strict=True)
    if network.version != 4 or not network.is_private or network.prefixlen < 24:
        raise ValueError('APP_SUBNET must be a private IPv4 /24 or smaller network.')
    if values.get('BACKGROUND_INGESTION') != 'true':
        raise ValueError('Keep BACKGROUND_INGESTION=true for this worker deployment.')
    return domain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', help='Your actual DNS hostname, such as your-name.duckdns.org')
    parser.add_argument('--reuse-backend-key', action='store_true', help='Read the existing local backend/.env key; requires python-dotenv')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        if args.check:
            domain = check_env()
        else:
            if not args.domain:
                parser.error('--domain is required to create configuration')
            if args.reuse_backend_key:
                from dotenv import dotenv_values
                key = dotenv_values(HERE.parents[1] / 'backend' / '.env').get('ANTHROPIC_API_KEY') or ''
            else:
                key = getpass('Existing Claude API key (hidden): ')
            write_env(args.domain, key)
            domain = check_env()
    except FileExistsError:
        raise SystemExit('Deployment .env already exists; it was not overwritten. Use --check or edit it deliberately.') from None
    except (ValueError, FileNotFoundError, ImportError) as exc:
        raise SystemExit(f'Configuration not ready: {exc}') from None
    print(f'Configuration ready for https://{domain}. Secrets were not printed.')


if __name__ == '__main__':
    main()
