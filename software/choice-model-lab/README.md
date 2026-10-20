# choice-model-lab

Conditional-logit estimation for repeated choice tasks. NumPy + SciPy, with an analytic gradient and Hessian.

```bash
python -m pip install -r requirements.txt
python -m choicelab
```

The default run generates 300 people × 4 tasks × 3 alternatives. It compares cost-only features with a price–loyalty interaction. Output is saved to [`examples/run.json`](examples/run.json).

## Input

Long-format CSV with one row per alternative

```csv
person_id,choice_id,alternative,chosen,price,walk,wait,price_x_loyalty
p01,q01,a,1,5,3,2,0
p01,q01,b,0,8,1,0,0
```

Every choice set needs exactly one chosen alternative. Alternative counts must be equal across sets. All rows for one person stay in either training or holdout, never both. Feature scaling is fitted on training data only.

```bash
python -m choicelab --csv input.csv --seed 17 --output results/run.json
```

## Estimation

For task `n`, alternative `a` has utility `X[n,a] @ beta`. Choice probabilities use a stable log-sum-exp. BFGS minimizes the summed negative log likelihood plus a small `1e-6` L2 term on scaled coefficients.

Standard errors use a sandwich covariance with score contributions aggregated by person. The output also includes convergence status, the Hessian condition number and the held-out accuracy, negative log likelihood and multiclass Brier score. The covariance is an asymptotic approximation; regularization, weak identification and a small number of people can make it unreliable. A pseudoinverse handles singular curvature but does not restore identification.

The synthetic data-generating coefficients are included in the output. In the committed seed-17 run, held-out negative log likelihood is about 0.543 for the cost-only model and 0.497 with the observed interaction. These numbers belong to this generated sample, not a transport survey or business deployment.

This is a fixed-coefficient model with an observed interaction. It does not estimate a random-coefficient Mixed Logit, latent attitudes or causal effects. Repeated tasks are clustered for uncertainty; this alone does not model serial dependence in the choice probabilities.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests compare derivatives with finite differences, recover parameters from a larger synthetic sample, check rescaling invariance, validate CSV input and verify that holdout groups do not overlap.

[`model.py`](choicelab/model.py) contains the estimator. [`data.py`](choicelab/data.py) contains the generator and CSV reader. The CLI saves enough information to inspect the split and fitted parameters without a notebook.
