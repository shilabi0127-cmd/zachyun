import argparse
import hashlib
import json
import platform
from pathlib import Path
import numpy as np
import scipy
from .data import synthetic,read_csv,FEATURES,TRUTH
from .model import fit,metrics,grouped_split


def run(x,y,groups,seed=17,synthetic_input=False):
    train,test=grouped_split(groups,seed=seed)
    results={}
    for name,indices in [('cost_only',[0,1,2]),('loyalty_interaction',[0,1,2,3])]:
        features=x[:,:,indices]
        fitted=fit(features[train],y[train],groups[train])
        results[name]={'coefficients':{FEATURES[i]:{'estimate':float(fitted.beta[j]),'cluster_robust_se':float(fitted.standard_errors[j])} for j,i in enumerate(indices)},'training':metrics(features[train],y[train],fitted.beta),'test':metrics(features[test],y[test],fitted.beta),'converged':fitted.converged,'optimizer_message':fitted.message,'hessian_condition_number':fitted.condition_number,'iterations':fitted.iterations}
    return {'input':'synthetic' if synthetic_input else 'user_csv','seed':seed,'choice_sets':len(y),'people':len(np.unique(groups)),'train_people':len(np.unique(groups[train])),'test_people':len(np.unique(groups[test])),'train_choice_sets':int(train.sum()),'test_choice_sets':int(test.sum()),'group_overlap':len(set(groups[train])&set(groups[test])),'split_hash':hashlib.sha256(json.dumps(sorted(map(str,np.unique(groups[test])))).encode()).hexdigest(),'synthetic_truth':dict(zip(FEATURES,TRUTH.tolist())) if synthetic_input else None,'versions':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},'models':results,'scope':'Conditional logit with observed interaction; not Mixed Logit, causal inference or a thesis replication.'}


def main():
    parser=argparse.ArgumentParser(description='Grouped holdout conditional-logit experiment')
    parser.add_argument('--csv',type=Path)
    parser.add_argument('--seed',type=int,default=17)
    parser.add_argument('--output',type=Path,default=Path('examples/run.json'))
    args=parser.parse_args()
    x,y,groups=read_csv(args.csv) if args.csv else synthetic(seed=args.seed)
    result=run(x,y,groups,args.seed,args.csv is None)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
