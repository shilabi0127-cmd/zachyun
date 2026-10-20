from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp


@dataclass
class Fit:
    beta:np.ndarray
    standard_errors:np.ndarray
    scale:np.ndarray
    converged:bool
    message:str
    condition_number:float
    iterations:int


def validate(x,y,groups):
    x=np.asarray(x,dtype=float);y=np.asarray(y);groups=np.asarray(groups)
    if x.ndim!=3 or x.shape[1]<2 or x.shape[2]<1:raise ValueError('X must have shape (choice_sets, alternatives, features)')
    if len(x)!=len(y) or len(x)!=len(groups) or not len(x):raise ValueError('Input lengths differ or are empty')
    if not np.all(np.isfinite(x)):raise ValueError('Features must be finite')
    if y.ndim!=1 or not np.issubdtype(y.dtype,np.integer) or np.any(y<0) or np.any(y>=x.shape[1]):raise ValueError('Chosen alternatives must be valid integer indices')
    return x,y,groups


def probabilities(x,beta):
    utility=np.einsum('nap,p->na',x,beta)
    return np.exp(utility-logsumexp(utility,axis=1,keepdims=True))


def loss_gradient(beta,x,y,l2=1e-6):
    utility=np.einsum('nap,p->na',x,beta)
    logs=utility-logsumexp(utility,axis=1,keepdims=True)
    p=np.exp(logs)
    loss=-logs[np.arange(len(y)),y].sum()+.5*l2*np.dot(beta,beta)
    gradient=np.einsum('na,nap->p',p,x)-x[np.arange(len(y)),y].sum(axis=0)+l2*beta
    return float(loss),gradient


def hessian(beta,x,l2=1e-6):
    p=probabilities(x,beta)
    mean=np.einsum('na,nap->np',p,x)
    return np.einsum('na,nap,naq->pq',p,x,x)-mean.T@mean+np.eye(x.shape[-1])*l2


def fit(x,y,groups,l2=1e-6):
    x,y,groups=validate(x,y,groups)
    if len(np.unique(groups))<5:raise ValueError('At least five training groups required')
    # No centering: alternative-invariant shifts cancel in softmax anyway.
    scale=x.std(axis=(0,1));scale=np.where(scale<1e-10,1.,scale)
    normalized=x/scale
    result=minimize(loss_gradient,np.zeros(x.shape[-1]),args=(normalized,y,l2),jac=True,method='BFGS',options={'gtol':1e-6,'maxiter':500})
    beta=result.x;curvature=hessian(beta,normalized,l2)
    condition=float(np.linalg.cond(curvature))
    inverse=np.linalg.pinv(curvature)
    p=probabilities(normalized,beta)
    scores=normalized[np.arange(len(y)),y]-np.einsum('na,nap->np',p,normalized)
    unique,inverse_group=np.unique(groups,return_inverse=True)
    clustered=np.zeros((len(unique),normalized.shape[-1]));np.add.at(clustered,inverse_group,scores)
    correction=len(unique)/(len(unique)-1)*(len(y)-1)/max(1,len(y)-x.shape[-1])
    covariance=inverse@(clustered.T@clustered)@inverse*correction
    se=np.sqrt(np.maximum(0,np.diag(covariance)))/scale
    return Fit(beta/scale,se,scale,bool(result.success),str(result.message),condition,int(result.nit))


def metrics(x,y,beta):
    p=probabilities(x,beta)
    return {'accuracy':float(np.mean(np.argmax(p,axis=1)==y)),
            'mean_negative_log_likelihood':float(-np.log(np.maximum(p[np.arange(len(y)),y],1e-300)).mean()),
            'brier_multiclass':float(np.mean(np.sum((p-np.eye(p.shape[1])[y])**2,axis=1)))}


def grouped_split(groups,test_fraction=.25,seed=17):
    if not 0<test_fraction<1:raise ValueError('test_fraction must be between 0 and 1')
    groups=np.asarray(groups);unique=np.unique(groups)
    if len(unique)<8:raise ValueError('At least eight independent groups required')
    shuffled=np.random.default_rng(seed).permutation(unique)
    count=max(1,min(len(unique)-5,round(len(unique)*test_fraction)))
    test=np.isin(groups,shuffled[:count])
    return ~test,test
