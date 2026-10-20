import os
from pathlib import Path
from threading import Lock
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from .index import Index
from .generation import answer
from .pipeline import run, ContextPolicy

ROOT=Path(__file__).resolve().parents[1]
NOTES=Path(os.environ.get('LOCAL_RESEARCH_NOTES',str(ROOT/'notes')))
INDEX=Index(os.environ.get('LOCAL_RESEARCH_DB',str(ROOT/'.local/index.sqlite')))
NOTES.mkdir(parents=True,exist_ok=True)
INDEX.ingest(NOTES)
write_lock=Lock()
app=FastAPI(title='Local Research Kit',version='0.1.0')


@app.middleware('http')
async def same_origin(request:Request,call_next):
    origin=request.headers.get('origin')
    if request.method=='POST' and origin and origin!=str(request.base_url).rstrip('/'):
        return Response('Same-origin requests only',status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'"
    return response


class Question(BaseModel):
    question:str=Field(min_length=1,max_length=1000)
    k:int=Field(default=4,ge=1,le=10)
    backend:str=Field(default='extractive',pattern='^(extractive|ollama|gguf)$')
    model:str=Field(default='',max_length=100,pattern=r'^[A-Za-z0-9_.:/-]*$')
    context_chars:int=Field(default=2600,ge=128,le=8000)

    @field_validator('question')
    @classmethod
    def not_blank(cls,value):
        if not value.strip():raise ValueError('Question cannot be blank')
        return value


class Document(BaseModel):
    name:str=Field(pattern=r'^[A-Za-z0-9_\u4e00-\u9fff-]{1,60}\.(md|txt)$')
    content:str=Field(min_length=1,max_length=100000)


@app.get('/api/status')
def status():
    return {**INDEX.stats(),'gguf_configured':bool(os.environ.get('LOCAL_RESEARCH_GGUF')),'version':'0.1.0'}


@app.post('/api/ask')
def ask(body:Question):
    return run(INDEX,body.question,body.k,body.backend,body.model,ContextPolicy(max_chars=body.context_chars))


@app.post('/api/documents')
def upload(body:Document):
    with write_lock:
        path=NOTES/body.name
        if path.is_symlink():raise HTTPException(422,'Symlinks are not accepted')
        path.write_text(body.content,encoding='utf-8')
        return INDEX.ingest(NOTES)


@app.get('/')
def home():return FileResponse(ROOT/'web/index.html')


app.mount('/web',StaticFiles(directory=ROOT/'web'),name='web')
