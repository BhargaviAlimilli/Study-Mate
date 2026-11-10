"""Check the deployed HTTPS routes without credentials or paid model calls."""
import argparse
import json
import urllib.error
import urllib.request
from urllib.parse import urlparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', help='https://your-name.duckdns.org')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    parts = urlparse(base)
    if parts.scheme != 'https' or not parts.netloc or parts.path or parts.username or parts.password or parts.query or parts.fragment:
        raise SystemExit('Provide an HTTPS origin without credentials, query, or path.')
    outcomes = []
    for path, expected in [('/', 200), ('/api/health', 200), ('/api/auth/me', 401)]:
        request = urllib.request.Request(base + path, headers={'User-Agent': 'StudyMate-deployment-check'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
                if path == '/api/health':
                    assert json.load(response).get('status') == 'ok', 'Unexpected health response'
                elif path == '/':
                    assert 'Study Mate' in response.read(128_000).decode('utf-8'), 'Unexpected frontend response'
        except urllib.error.HTTPError as error:
            status = error.code
        outcomes.append({'path': path, 'expected': expected, 'actual': status})
    print(json.dumps(outcomes, indent=2))
    raise SystemExit(0 if all(item['expected'] == item['actual'] for item in outcomes) else 1)


if __name__ == '__main__':
    main()
