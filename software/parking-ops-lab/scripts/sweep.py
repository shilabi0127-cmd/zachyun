"""Reproducible admission/risk sensitivity experiment; synthetic data only."""
import json
import platform
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import scipy
from parkinglab.domain import sample_reservations, ExperimentConfig, ExperimentRequest
from parkinglab.simulation import run_experiment


def main():
    results=[]
    for count in [48,100,300]:
        for risk in [.05,.1,.2]:
            req=ExperimentRequest(reservations=sample_reservations(count),config=ExperimentConfig(slots=4,risk_budget=risk,trials=500))
            result=run_experiment(req)
            results.append({'count':count,'risk_budget':risk,'scenario_hash':result['scenario_hash'],
                'runtime_ms':result['total_runtime_ms'],'policies':{key:{k:v for k,v in p.items() if k!='schedule'} for key,p in result['policies'].items()}})
    output={'environment':{'python':platform.python_version(),'platform':platform.platform(),'numpy':np.__version__,'scipy':scipy.__version__},'note':'Single local run; not a rigorous speed benchmark or real-world traffic evidence.','runs':results}
    path=Path(__file__).resolve().parents[1]/'docs'/'sensitivity.json'
    path.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps([{'n':r['count'],'alpha':r['risk_budget'],'ms':r['runtime_ms'],'buffered_accepted':r['policies']['buffered_milp']['accepted'],'buffered_conflict':r['policies']['buffered_milp']['conflict_rate']} for r in results]))


if __name__=='__main__':main()
