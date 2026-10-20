import argparse
import json
from pathlib import Path
from .index import Index
from .generation import answer
from .pipeline import run, replay, save_record, ContextPolicy


def main():
    parser=argparse.ArgumentParser(description='Search local Markdown notes with source lines')
    parser.add_argument('command',choices=['index','ask','evaluate','replay'])
    parser.add_argument('question',nargs='?',default='')
    parser.add_argument('--notes',type=Path,default=Path('notes'))
    parser.add_argument('--db',type=Path,default=Path('.local/index.sqlite'))
    parser.add_argument('--backend',choices=['extractive','ollama','gguf'],default='extractive')
    parser.add_argument('--model',default='')
    parser.add_argument('--context-chars',type=int,default=2600)
    parser.add_argument('--record',type=Path)
    args=parser.parse_args()
    if args.command=='replay':
        result=replay(json.loads(Path(args.question).read_text(encoding='utf-8')),args.backend,args.model)
    else:
        index=Index(args.db)
        if args.command=='index':result=index.ingest(args.notes)
        elif args.command=='ask':result=run(index,args.question,backend=args.backend,model=args.model,policy=ContextPolicy(max_chars=args.context_chars))
        else:
            from .evaluation import evaluate
            index.ingest(args.notes);result=evaluate(index,Path('evaluation.jsonl'))
    if args.record:save_record(result,args.record)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
