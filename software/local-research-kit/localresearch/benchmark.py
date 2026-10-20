"""Record generation and citation checks without treating them as factual accuracy."""
import argparse
import json
import time
from pathlib import Path
from .index import Index
from .generation import answer


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--backend',choices=['gguf','ollama'],required=True)
    parser.add_argument('--model',default='')
    parser.add_argument('--output',type=Path,default=Path('docs/generation-run.json'))
    args=parser.parse_args()
    index=Index('.local/index.sqlite');index.ingest('notes')
    cases=['共同随机数有什么作用','为什么按受访者划分测试集','樱桃蛋糕烘焙配方']
    rows=[]
    for question in cases:
        start=time.perf_counter()
        result=answer(index,question,k=2,backend=args.backend,model=args.model)
        rows.append({'seconds':round(time.perf_counter()-start,3),**result})
    generated=[r for r in rows if r['generated']]
    report={'backend':args.backend,'model_label':args.model,'cases':rows,
            'generated_cases':len(generated),'nonempty_generated_cases':sum(bool(r['items']) for r in generated),
            'filtered_items':sum(r['rejected_items'] for r in rows),
            'note':'A few local smoke cases. Exact quote/source validation is not semantic factuality evaluation. First request includes model loading.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'},ensure_ascii=False))


if __name__=='__main__':main()
