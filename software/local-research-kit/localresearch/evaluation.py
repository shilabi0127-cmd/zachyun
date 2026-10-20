"""Transparent, document-level retrieval checks, not a model leaderboard."""
import json


def evaluate(index,path,k=4):
    cases=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    records=[];positive=0;recall=0.;rr=0.;negative=0;refused=0
    for case in cases:
        hits=index.search(case['question'],k)
        ranks=[i+1 for i,h in enumerate(hits) if h['path'] in case['expected_paths']]
        if case['expected_paths']:
            positive+=1;recall+=bool(ranks);rr+=1/min(ranks) if ranks else 0
        else:
            negative+=1;refused+=not hits
        records.append({'question':case['question'],'expected_paths':case['expected_paths'],'retrieved_paths':[h['path'] for h in hits],'first_relevant_rank':min(ranks) if ranks else None})
    return {'k':k,'positive_cases':positive,'negative_cases':negative,'hit_rate_at_k':recall/positive if positive else None,'mrr_at_k':rr/positive if positive else None,'empty_retrieval_rate_on_negative_cases':refused/negative if negative else None,'cases':records,'scope':'Hand-written smoke set over bundled notes; not independent generalization evidence.'}
