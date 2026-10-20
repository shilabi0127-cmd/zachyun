import argparse
import json
from pathlib import Path
from .index import Index
from .generation import answer


def main():
    parser=argparse.ArgumentParser(description='Search local Markdown notes with source lines')
    parser.add_argument('command',choices=['index','ask','evaluate'])
    parser.add_argument('question',nargs='?',default='')
    parser.add_argument('--notes',type=Path,default=Path('notes'))
    parser.add_argument('--db',type=Path,default=Path('.local/index.sqlite'))
    parser.add_argument('--backend',choices=['extractive','ollama','gguf'],default='extractive')
    parser.add_argument('--model',default='')
    args=parser.parse_args();index=Index(args.db)
    if args.command=='index':result=index.ingest(args.notes)
    elif args.command=='ask':result=answer(index,args.question,backend=args.backend,model=args.model)
    else:
        from .evaluation import evaluate
        index.ingest(args.notes);result=evaluate(index,Path('evaluation.jsonl'))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
