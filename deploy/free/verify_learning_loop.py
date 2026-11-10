"""Owner-operated live check. Creates a synthetic PDF, conversation and quiz; uses Claude credits.

Reads only the ignored local .env.owner-login JSON. Never prints credentials.
Retains demonstration data in the owner's account. Run after check_public.py.
"""
import json
from pathlib import Path
import time

import httpx


HERE = Path(__file__).resolve().parent


def sample_pdf():
    lines = [
        'StudyMate Deployment Check: Python asyncio',
        'Asyncio coordinates concurrent I/O-bound tasks with cooperative scheduling.',
        'Calling an async def function returns a coroutine object.',
        'Await suspends the current coroutine until its awaited operation completes.',
        'Other ready tasks can run while a coroutine awaits non-blocking I/O.',
        'Asyncio.run starts an event loop, runs the main coroutine and closes the loop.',
        'Asyncio.create_task schedules a coroutine to run concurrently in the loop.',
        'Asyncio.gather awaits operations and returns results in input order.',
        'Asyncio.sleep yields control without blocking the event loop thread.',
        'Time.sleep blocks the thread and delays other tasks on that loop.',
        'CPU-heavy synchronous work can block the loop; use another executor.',
        'Cancelling a task raises CancelledError inside its coroutine.',
        'Try and finally can release resources when cancellation interrupts a task.',
        'Concurrency coordinates overlapping tasks without requiring CPU parallelism.',
    ]
    stream = 'BT /F1 10 Tf 40 790 Td 15 TL\n'
    for i, line in enumerate(lines):
        escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        stream += ('T* ' if i else '') + f'({escaped}) Tj\n'
    stream += 'ET'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        f'<< /Length {len(stream.encode())} >>\nstream\n{stream}\nendstream'.encode(),
    ]
    pdf = b'%PDF-1.4\n'
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(pdf)
    pdf += b'xref\n0 6\n0000000000 65535 f \n'
    pdf += b''.join(f'{n:010d} 00000 n \n'.encode() for n in offsets)
    return pdf + f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


def main():
    credentials = json.loads((HERE / '.env.owner-login').read_text())
    results = {'url': credentials['url'], 'checks': []}

    def passed(name):
        results['checks'].append(name)
        print(name, 'passed', flush=True)
        results['checked_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        (HERE / 'LIVE_VERIFICATION.json').write_text(json.dumps(results, indent=2))

    def checked(response, expected=200):
        if response.status_code != expected:
            # These app endpoints do not echo passwords or bearer tokens in errors.
            raise RuntimeError(f'{response.request.method} {response.request.url.path}: '
                               f'{response.status_code}: {response.text[:600]}')
        return response

    with httpx.Client(base_url=credentials['url'] + '/api', timeout=180) as client:
        login = checked(client.post('/auth/login', json={
            'email': credentials['email'], 'password': credentials['password']})).json()
        client.headers['Authorization'] = 'Bearer ' + login['access_token']
        checked(client.get('/auth/me'))
        passed('login_and_token_validation')
        checked(client.post('/auth/register', json={'name': 'Deployment Check',
            'email': 'deployment-check@example.com', 'password': 'Synthetic9!Password'}), 403)
        passed('public_registration_disabled')
        docs = checked(client.get('/documents')).json()
        existing = next((d for d in docs if d['filename'] == 'Deployment_Check_Asyncio.pdf'), None)
        if existing:
            document_id = existing['id']
        else:
            upload = checked(client.post('/documents/upload', files={
                'file': ('Deployment_Check_Asyncio.pdf', sample_pdf(), 'application/pdf')}), 202).json()
            document_id = upload['document_id']
        results['document_id'] = document_id
        for i in range(120):
            state = checked(client.get('/documents/' + document_id)).json()
            if state['status'] == 'ready':
                break
            if state['status'] == 'failed':
                raise RuntimeError('Worker ingestion failed; inspect server logs.')
            if i % 6 == 0:
                print('Worker ingestion:', state['status'], flush=True)
            time.sleep(5)
        else:
            raise RuntimeError('Worker ingestion timed out.')
        assert state['chunks_stored'] > 0
        passed('queued_ingestion_and_qdrant_embeddings')
        for suffix in ['/file', '/file?page=1']:
            assert checked(client.get('/documents/' + document_id + suffix)).content.startswith(b'%PDF-')
        passed('pdf_original_and_page_open')
        reply = checked(client.post('/query', json={'query':
            'Explain how await and asyncio.sleep affect the event loop.',
            'document_id': document_id, 'action': 'answer'})).json()
        assert reply['status'] == 'answered', reply['status']
        results['conversation_id'] = reply['conversation_id']
        messages = checked(client.get('/conversations/' + reply['conversation_id'] + '/messages')).json()
        assert len(messages) >= 2
        passed('claude_answer_and_saved_conversation')
        quiz = checked(client.post('/quizzes', json={
            'topic': 'Python asyncio tasks, scheduling, await, sleep and cancellation',
            'question_count': 5, 'document_id': document_id}), 201).json()
        assert len(quiz['questions']) == 5
        results['quiz_id'] = quiz['id']
        passed('quiz_generation')
        attempt = checked(client.post('/quizzes/' + quiz['id'] + '/submit', json={
            'answers': [{'question_id': q['id'], 'selected_index': 0}
                        for q in quiz['questions']]}), 201).json()
        assert attempt['total'] == 5 and attempt['feedback']['summary']
        assert all(answer['sources'] for answer in attempt['answers'])
        results['attempt_id'] = attempt['id']
        checked(client.get('/quizzes/' + quiz['id'] + '/attempts/' + attempt['id']))
        passed('quiz_submission_feedback_and_pdf_sources')
        for path in ['/progress', '/revisions', '/progress/recommendations']:
            checked(client.get(path))
        passed('progress_and_revision_endpoints')
        checked(client.post('/auth/logout'))
        checked(client.get('/auth/me'), 401)
        passed('logout_revocation')


if __name__ == '__main__':
    main()
