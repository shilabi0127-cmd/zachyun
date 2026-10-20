import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from fastapi.testclient import TestClient
from parkinglab.api import app
from parkinglab import ollama

client=TestClient(app)


def test_api_workflow():
    assert client.get('/').status_code==200
    assert client.get('/api/health').json()['solver']=='SciPy / HiGHS'
    rows=client.post('/api/import',json={'csv_text':'id,start,end\na,08:00,09:00\nb,09:00,10:00'}).json()['reservations']
    response=client.post('/api/solve',json={'reservations':rows,'config':{'slots':1,'trials':50}})
    assert response.status_code==200
    data=response.json()
    assert len(data['policies'])==3
    report=client.post('/api/report',json={'run_id':data['run_id']})
    assert report.status_code==200 and data['scenario_hash'] in report.json()['report']
    assert client.post('/api/report',json={'run_id':'missing'}).status_code==404


def test_api_validation_and_origin():
    assert client.post('/api/import',json={'csv_text':'bad'}).status_code==422
    assert client.post('/api/solve',json={'reservations':[]}).status_code==422
    assert client.post('/api/import',json={'csv_text':'bad'},headers={'Origin':'https://example.org'}).status_code==403
    assert client.get('/static/app.js').headers['x-content-type-options']=='nosniff'


@pytest.mark.parametrize('url',['https://example.com','http://192.168.1.2:11434','http://127.0.0.1:11434/path','http://user@localhost:11434'])
def test_adapter_rejects_remote_hosts(monkeypatch,url):
    monkeypatch.setenv('PARKINGLAB_OLLAMA_URL',url)
    with pytest.raises(ValueError):ollama.base_url()


def test_ollama_contract(monkeypatch):
    captured={}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            assert self.path=='/api/tags'
            self.send_response(200);self.end_headers();self.wfile.write(b'{"models":[{"name":"local-test"}]}')
        def do_POST(self):
            captured.update(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200);self.end_headers();self.wfile.write(b'{"message":{"content":"test explanation"}}')
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setenv('PARKINGLAB_OLLAMA_URL',f'http://127.0.0.1:{server.server_port}')
    try:
        assert ollama.models()['models']==['local-test']
        assert ollama.explain({'config':{},'policies':{'fcfs':{'accepted':1,'schedule':[{'secret':'raw'}]}}},'local-test')=='test explanation'
        assert captured['stream'] is False
        assert 'schedule' not in captured['messages'][1]['content']
        assert 'secret' not in captured['messages'][1]['content']
    finally:
        server.shutdown();server.server_close();thread.join()


def test_ollama_unavailable(monkeypatch):
    monkeypatch.setenv('PARKINGLAB_OLLAMA_URL','http://127.0.0.1:1')
    assert ollama.models()['available'] is False
