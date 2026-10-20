import csv
from pathlib import Path
import numpy as np
from .model import probabilities,validate

FEATURES=['price','walk','wait','price_x_loyalty']
TRUTH=np.array([-.35,-.07,-.06,-.65])


def synthetic(people=300,tasks=4,seed=17):
    rng=np.random.default_rng(seed)
    groups=np.repeat(np.arange(people),tasks)
    loyalty=np.repeat(rng.integers(0,2,people),tasks)
    price=rng.uniform(2,15,size=(len(groups),3))
    walk=rng.uniform(1,15,size=price.shape)
    wait=rng.uniform(0,8,size=price.shape)
    x=np.stack([price,walk,wait,price*loyalty[:,None]],axis=-1)
    p=probabilities(x,TRUTH)
    y=np.sum(rng.random(len(groups))[:,None]>np.cumsum(p,axis=1),axis=1).clip(max=2)
    return x,y,groups


def read_csv(path,features=FEATURES):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        required={'person_id','choice_id','alternative','chosen',*features}
        if not reader.fieldnames or not required<=set(reader.fieldnames):raise ValueError('Missing required columns')
        cases={}
        for line,row in enumerate(reader,2):
            try:
                person=row['person_id'];choice=row['choice_id'];alt=row['alternative']
                chosen=int(row['chosen'])
                if not person or not choice or not alt or chosen not in (0,1):raise ValueError('Invalid ID or chosen value')
                entries=cases.setdefault((person,choice),{})
                if alt in entries:raise ValueError('Duplicate alternative within a choice set')
                entries[alt]=([float(row[f]) for f in features],chosen)
            except (ValueError,KeyError) as error:raise ValueError(f'CSV line {line}: {error}') from error
            if line>100001:raise ValueError('CSV exceeds 100000 rows')
    x=[];y=[];groups=[];count=None
    for (person,_),entries in cases.items():
        ordered=sorted(entries.items())
        if count is None:count=len(ordered)
        if len(ordered)!=count:raise ValueError('All choice sets must have equal alternative counts')
        if sum(v[1] for _,v in ordered)!=1:raise ValueError('Each choice set must have exactly one chosen alternative')
        x.append([v[0] for _,v in ordered]);y.append(next(i for i,(_,v) in enumerate(ordered) if v[1]));groups.append(person)
    return validate(np.asarray(x),np.asarray(y),np.asarray(groups))
