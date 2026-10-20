import importlib
from fastapi.testclient import TestClient


def test_api_upload_ask(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCAL_RESEARCH_NOTES',str(tmp_path/'notes'))
    monkeypatch.setenv('LOCAL_RESEARCH_DB',str(tmp_path/'test.sqlite'))
    import localresearch.api
    module=importlib.reload(localresearch.api)
    client=TestClient(module.app)
    assert client.get('/').status_code==200
    assert client.post('/api/documents',json={'name':'note.md','content':'# 共同随机数\n共同随机数使用同一批随机样本进行策略比较。'}).status_code==200
    data=client.post('/api/ask',json={'question':'共同随机数'}).json()
    assert data['hits'][0]['path']=='note.md'
    assert client.post('/api/documents',json={'name':'../escape.md','content':'bad'}).status_code==422
    assert client.post('/api/ask',json={'question':'abc'},headers={'Origin':'https://example.com'}).status_code==403
