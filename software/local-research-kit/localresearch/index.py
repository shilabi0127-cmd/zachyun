"""SQLite FTS5 index with Chinese bigrams and source line references."""
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def terms(text):
    out = re.findall(r"[a-z0-9_]{2,}", text.lower())
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        out.extend(run[i:i+2] for i in range(len(run)-1))
        if len(run) == 1:
            out.append(run)
    return out


def chunks(text, max_chars=650):
    """Keep headings and complete source lines; split long lines explicitly."""
    heading, buffer, start = "", [], 1
    for line_no, line in enumerate(text.splitlines(), 1):
        if line.startswith("#"):
            if buffer:
                yield heading, start, line_no-1, "\n".join(buffer)
                buffer=[]
            heading=line.lstrip("# ")
        if buffer and sum(len(x)+1 for x in buffer)+len(line)>max_chars:
            yield heading, start, line_no-1, "\n".join(buffer)
            buffer=[]
        if not buffer:start=line_no
        if len(line)>max_chars:
            if buffer:
                yield heading,start,line_no-1,"\n".join(buffer)
                buffer=[]
            for offset in range(0,len(line),max_chars):
                yield heading,line_no,line_no,line[offset:offset+max_chars]
            start=line_no+1
        else:buffer.append(line)
    if buffer and "\n".join(buffer).strip():
        yield heading,start,len(text.splitlines()),"\n".join(buffer)


class Index:
    def __init__(self, database):
        self.database=Path(database)
        self.database.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS docs(path TEXT PRIMARY KEY, sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,path TEXT NOT NULL,heading TEXT,start_line INTEGER,end_line INTEGER,text TEXT);
                CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED,terms,tokenize='unicode61');
            ''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.database,timeout=10)
        db.row_factory=sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, root):
        root=Path(root).resolve()
        if not root.is_dir():raise ValueError("Document directory does not exist")
        files=[]
        for path in sorted(root.rglob('*')):
            if path.is_symlink() or path.suffix.lower() not in {'.md','.txt'} or not path.is_file():continue
            if not path.resolve().is_relative_to(root):continue
            if path.stat().st_size>1_000_000:raise ValueError("Document exceeds 1 MB: "+path.name)
            files.append(path)
            if len(files)>500:raise ValueError("Maximum 500 text documents")
        changed=0
        with self.connect() as db:
            live={p.relative_to(root).as_posix() for p in files}
            old={row['path']:row['sha256'] for row in db.execute('SELECT * FROM docs')}
            for name in set(old)-live:self._remove(db,name)
            for path in files:
                name=path.relative_to(root).as_posix()
                raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
                if old.get(name)==digest:continue
                text=raw.decode('utf-8-sig')
                self._remove(db,name)
                db.execute('INSERT INTO docs VALUES (?,?)',(name,digest))
                for sequence,(heading,start,end,content) in enumerate(chunks(text)):
                    chunk_id=hashlib.sha256((name+'\0'+digest+'\0'+str(sequence)).encode()).hexdigest()[:16]
                    db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?)',(chunk_id,name,heading,start,end,content))
                    db.execute('INSERT INTO search VALUES (?,?)',(chunk_id,' '.join(terms(content))))
                changed+=1
            total=db.execute('SELECT count(*) FROM chunks').fetchone()[0]
        return {'documents':len(files),'updated':changed,'chunks':total}

    @staticmethod
    def _remove(db,name):
        db.execute('DELETE FROM search WHERE id IN (SELECT id FROM chunks WHERE path=?)',(name,))
        db.execute('DELETE FROM chunks WHERE path=?',(name,))
        db.execute('DELETE FROM docs WHERE path=?',(name,))

    def search(self,question,k=4):
        if not 1<=k<=10:raise ValueError('k must be 1..10')
        tokens=sorted(set(terms(question)))[:60]
        if not tokens:return []
        expression=' OR '.join('"'+t.replace('"','""')+'"' for t in tokens)
        with self.connect() as db:
            rows=db.execute('''SELECT c.*,bm25(search) AS rank FROM search JOIN chunks c ON c.id=search.id
                               WHERE search MATCH ? ORDER BY rank,c.id LIMIT ?''',(expression,k*3)).fetchall()
        hits=[]
        for row in rows:
            hit=dict(row)
            overlap=set(tokens)&set(terms(hit['text']))
            hit['query_coverage']=len(overlap)/len(tokens)
            # This lexical filter is a heuristic, not a calibrated confidence.
            if hit['query_coverage']<.12:continue
            hit['score']=-hit.pop('rank')
            hits.append(hit)
        return hits[:k]

    def stats(self):
        with self.connect() as db:
            return {'documents':db.execute('SELECT count(*) FROM docs').fetchone()[0],
                    'chunks':db.execute('SELECT count(*) FROM chunks').fetchone()[0]}
