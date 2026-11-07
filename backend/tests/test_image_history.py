from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.routes import media
from app.models.conversation import Message
from test_auth import auth_client, register, login


def test_image_exchange_persists_and_is_private_and_replay_safe(auth_client, monkeypatch):
    http, engine = auth_client
    register(http)
    headers = {'Authorization': 'Bearer ' + login(http).json()['access_token']}
    monkeypatch.setattr(media, 'create_agent', lambda **kwargs: object())
    call = AsyncMock(return_value=SimpleNamespace(final_output={'status':'answered','answer':'This image shows a study diagram.'}))
    monkeypatch.setattr(media.Runner,'run',call)
    output = BytesIO(); Image.new('RGB',(20,20),'green').save(output,format='PNG'); image = output.getvalue()
    request_id = str(uuid4())
    data = {'query':'Explain this diagram','request_id':request_id}
    def send(): return http.post('/media/image-query',headers=headers,data=data,files={'file':('diagram.png',image,'image/png')})
    first = send()
    assert first.status_code == 200, first.text
    conversation = first.json()['conversation_id']
    assert first.json()['grounding'] == 'uploaded_image'
    repeated = send()
    assert repeated.json() == first.json() and call.call_count == 1
    messages = http.get(f'/conversations/{conversation}/messages',headers=headers).json()
    assert len(messages) == 2
    assert messages[0]['image_name'] == 'diagram.png'
    assert messages[-1]['grounding'] == 'uploaded_image'
    url = messages[0]['image_url']
    saved = http.get(url,headers=headers)
    assert saved.content == image and saved.headers['content-type'] == 'image/png'
    assert saved.headers['cache-control'] == 'no-store'
    with Session(engine) as db:
        assert db.scalar(select(Message).where(Message.role == 'user')).image_content == image
    http.post('/auth/register', json={'name':'Other','email':'other@example.com','password':'CorrectHorse123!'})
    other = http.post('/auth/login',json={'email':'other@example.com','password':'CorrectHorse123!'}).json()['access_token']
    assert http.get(url,headers={'Authorization': 'Bearer '+other}).status_code == 404
    data['query'] = 'A different request'
    assert send().status_code == 409


def test_bad_image_and_foreign_conversation_do_not_call_provider(auth_client, monkeypatch):
    http, engine = auth_client
    register(http)
    headers = {'Authorization': 'Bearer ' + login(http).json()['access_token']}
    monkeypatch.setattr(media,'create_agent',lambda **kwargs: object())
    call = AsyncMock(); monkeypatch.setattr(media.Runner,'run',call)
    assert http.post('/media/image-query',headers=headers,files={'file':('image.png',b'not an image','image/png')}).status_code == 400
    output=BytesIO(); Image.new('RGB',(10,10)).save(output,format='PNG')
    assert http.post('/media/image-query',headers=headers,data={'conversation_id':str(uuid4())},files={'file':('image.png',output.getvalue(),'image/png')}).status_code == 404
    call.assert_not_called()
