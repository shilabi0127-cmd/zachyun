import numpy as np
import pytest
from choicelab.model import probabilities,loss_gradient,hessian,fit,grouped_split,validate
from choicelab.data import synthetic,TRUTH,read_csv
from choicelab.__main__ import run


def test_probabilities_stable():
    x=np.array([[[10000.],[-10000.],[9999.]]])
    p=probabilities(x,np.ones(1))
    assert np.isfinite(p).all() and np.isclose(p.sum(),1)


def test_gradient_and_hessian_match_finite_differences():
    x,y,_=synthetic(10,2)
    beta=np.array([-.2,-.1,-.1,-.4])
    step=1e-5
    basis=np.eye(len(beta))*step
    numeric=np.array([(loss_gradient(beta+d,x,y)[0]-loss_gradient(beta-d,x,y)[0])/(2*step) for d in basis])
    assert np.allclose(numeric,loss_gradient(beta,x,y)[1],rtol=1e-5,atol=1e-5)
    numeric_h=np.column_stack([(loss_gradient(beta+d,x,y)[1]-loss_gradient(beta-d,x,y)[1])/(2*step) for d in basis])
    assert np.allclose(numeric_h,hessian(beta,x),rtol=1e-5,atol=1e-5)


def test_grouped_split_has_no_leakage():
    _,_,groups=synthetic(30,4)
    train,test=grouped_split(groups)
    assert not set(groups[train])&set(groups[test])
    assert np.all(train^test)
    assert np.array_equal(test,grouped_split(groups)[1])


def test_parameter_recovery_on_large_synthetic_sample():
    x,y,groups=synthetic(1500,4,seed=6)
    fitted=fit(x,y,groups)
    assert np.allclose(fitted.beta,TRUTH,atol=.08)
    assert np.all(np.isfinite(fitted.standard_errors))
    assert np.all(fitted.standard_errors>0)


def test_feature_rescaling_preserves_predictions():
    x,y,g=synthetic(100,2)
    a=fit(x,y,g)
    scaled=x.copy();scaled[:,:,0]*=100
    b=fit(scaled,y,g)
    assert np.allclose(probabilities(x,a.beta),probabilities(scaled,b.beta),atol=1e-6)


def test_holdout_pipeline():
    result=run(*synthetic(60,3),synthetic_input=True)
    assert result['group_overlap']==0
    assert len(result['models'])==2
    assert result['models']['loyalty_interaction']['test']['mean_negative_log_likelihood']>0


def test_csv_validation(tmp_path):
    path=tmp_path/'data.csv'
    path.write_text('person_id,choice_id,alternative,chosen,price,walk,wait,price_x_loyalty\na,q1,1,1,5,2,1,0\na,q1,2,0,6,1,1,0')
    x,y,g=read_csv(path)
    assert x.shape==(1,2,4) and y[0]==0
    path.write_text(path.read_text().replace('q1,2,0','q1,2,1'))
    with pytest.raises(ValueError):read_csv(path)


def test_invalid_inputs():
    with pytest.raises(ValueError):validate(np.ones((3,2,1)),np.array([0,1,2]),np.arange(3))
    with pytest.raises(ValueError):grouped_split(np.array([1,2]))
