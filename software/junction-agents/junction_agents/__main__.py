import argparse
import json
from pathlib import Path
from .experiment import train,evaluate


def main():
    parser=argparse.ArgumentParser(description="Multi-junction agent-control experiments")
    parser.add_argument('command',choices=['train','evaluate'])
    parser.add_argument('--episodes',type=int)
    parser.add_argument('--checkpoint',type=Path,default=Path('examples/checkpoint.json'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--seed-start',type=int,default=60000)
    args=parser.parse_args()
    if args.command=='train':
        result=train(args.episodes or 800);output=args.output or args.checkpoint
    else:
        result=evaluate(json.loads(args.checkpoint.read_text(encoding='utf-8')),args.episodes or 25,args.seed_start)
        output=args.output or Path('examples/evaluation.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'q','history','episodes'}},indent=2))


if __name__=='__main__':main()
