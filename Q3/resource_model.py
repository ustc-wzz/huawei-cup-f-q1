"""Q3 deterministic conditional optimization. N,D use billions; C uses FLOPs."""
from dataclasses import dataclass
from functools import lru_cache
import numpy as np
from scipy.optimize import brentq, minimize_scalar

COSTS = ('exponential', 'power', 'logarithmic')
COST_LABELS = dict(zip(COSTS, ['指数成本', '幂函数成本', '对数成本']))
ETA_ATT = 2e-4
QUALITY_TOL = 1e-7
OBJECTIVE_RTOL = 1e-9

def g(z, kind):
    if kind == 'exponential': return 1e7 * np.exp(6*z)
    if kind == 'power': return 5e9 * z**4
    if kind == 'logarithmic': return 2e9 * np.log1p(10*z)
    raise ValueError(kind)

def gp(z, kind):
    if kind == 'exponential': return 6e7 * np.exp(6*z)
    if kind == 'power': return 2e10 * z**3
    if kind == 'logarithmic': return 2e10 / (1+10*z)
    raise ValueError(kind)

@dataclass(frozen=True)
class Scenario:
    recipe: str
    q0: float
    h: float
    cap: float
    s_q: float = 1.
    keep: float = .5
    mapping: str = 'A1_balanced_q01_q99'
    lo: float = -1.0324670105580689
    hi: float = .6452932807676527

class ResourceModel:
    def __init__(self, interface):
        self.par = interface['B1']
        self.E, self.A, self.B = (self.par[k] for k in ['E','A','B'])
        self.alpha, self.nu = (self.par[k] for k in ['alpha','nu'])
        self.theta, self.eta = interface['theta_Q'], interface['eta']
        assert self.A > 0 and self.B > 0 and self.alpha > 0 and self.nu > 0

    def details(self, N, D, u, ctx, cost, sc):
        z0=(sc.q0-sc.lo)/(sc.hi-sc.lo); z=(sc.q0+u-sc.lo)/(sc.hi-sc.lo)
        assert 0 < z0 <= z+1e-12 <= 1+1e-12
        c=1e9*max(0.,float(g(z,cost)-g(z0,cost)))
        tn=self.A*N**(-self.alpha); td=self.B*D**(-self.nu)
        factor=np.exp(-self.theta/sc.s_q*u+self.eta*sc.h)
        train=6e18*N*D; att=ETA_ATT*ctx*1e18*N*D; quality=c*D
        return dict(N_B=float(N),D_B=float(D),u=float(u),Q=sc.q0+float(u),z=float(z),
                    z0=float(z0),u_max=sc.cap,t=float(u/sc.cap),tn=float(tn),td=float(td),
                    reducible_loss=float((tn+td)*factor),loss=float(self.E+(tn+td)*factor),
                    C_train=float(train),C_att=float(att),C_quality=float(quality),c=float(c))

    def inner(self, C, ctx, cost, sc, u, bracket_padding=1.):
        k=1e18*(6+ETA_ATT*ctx)
        z0=(sc.q0-sc.lo)/(sc.hi-sc.lo); z=(sc.q0+u-sc.lo)/(sc.hi-sc.lo)
        c=1e9*max(0.,float(g(z,cost)-g(z0,cost)))
        x0=(np.log(self.alpha*self.A/(self.nu*self.B))+self.nu*np.log(C/k))/(self.alpha+self.nu)
        def balance(x):
            logden=np.logaddexp(np.log(k)+x, np.log(c) if c>0 else -np.inf)
            logD=np.log(C)-logden
            return np.log(self.alpha*self.A)-self.alpha*x-np.log(self.nu*self.B)+self.nu*logD-(np.log(k)+x-logden)
        lo=x0-bracket_padding; hi=x0+bracket_padding; expansions=0
        while balance(lo)<=0 or balance(hi)>=0:
            expansions+=1
            lo-=2**expansions; hi+=2**expansions
            if expansions>12:raise RuntimeError('Failed to bracket unique log-N optimum')
        x=brentq(balance,lo,hi,xtol=1e-12,rtol=1e-13)
        N=np.exp(x); D=C/(k*N+c)
        r=self.details(N,D,u,ctx,cost,sc)
        cp=1e9*gp(r['z'],cost)/(sc.hi-sc.lo)
        r.update(M=-self.theta/sc.s_q*(r['tn']+r['td'])+self.nu*r['td']*cp/(k*N+c),
                 kkt_log_residual=float(abs(balance(x))),bracket_expansions=expansions,
                 logN_margin=min(x-lo,hi-x))
        return r

    @lru_cache(maxsize=12000)
    def solve(self,C,ctx,cost,sc,grid=65):
        ts=np.linspace(0,1,grid)
        rr=[self.inner(C,ctx,cost,sc,float(t*sc.cap)) for t in ts]
        values=np.array([r['reducible_loss'] for r in rr])
        deriv=np.array([r['M'] for r in rr])
        candidates=[0.,1.]
        # Every detected stationary branch is compared, including maxima as a harmless extra.
        for i in range(grid-1):
            if deriv[i]*deriv[i+1]<0:
                root=brentq(lambda t:self.inner(C,ctx,cost,sc,t*sc.cap)['M'],ts[i],ts[i+1],xtol=1e-12)
                candidates.append(root)
        # Additional local refinement guards against poorly sampled stationary branches.
        for i in range(1,grid-1):
            if values[i]<=values[i-1] and values[i]<=values[i+1]:
                opt=minimize_scalar(lambda t:self.inner(C,ctx,cost,sc,t*sc.cap)['reducible_loss'],
                                    bounds=(ts[i-1],ts[i+1]),method='bounded',options={'xatol':1e-11})
                candidates.append(float(opt.x))
        unique=[]
        for t in sorted(candidates):
            if not unique or abs(t-unique[-1])>1e-6: unique.append(t)
        rows=[self.inner(C,ctx,cost,sc,t*sc.cap) for t in unique]
        best=min(rows,key=lambda x:x['reducible_loss']).copy()
        state=lambda t:'R0' if t<=QUALITY_TOL else 'R2' if t>=1-QUALITY_TOL else 'R1'
        tied=[r for r in rows if r['reducible_loss']-best['reducible_loss']<=OBJECTIVE_RTOL*max(best['reducible_loss'],1e-12)]
        best.update(C=C,L_ctx=ctx,cost=cost,recipe=sc.recipe,s_Q=sc.s_q,keep=sc.keep,mapping=sc.mapping,
                    state=state(best['t']),near_optimal_states='|'.join(sorted(set(state(r['t']) for r in tied))),
                    near_optimal_t_min=min(r['t'] for r in tied),near_optimal_t_max=max(r['t'] for r in tied),
                    candidate_count=len(rows),grid=grid)
        for key in ['train','att','quality']: best['share_'+key]=best['C_'+key]/C
        best['budget_relative_error']=abs(best['C_train']+best['C_att']+best['C_quality']-C)/C
        base=rr[0]
        best.update(baseline_loss=base['loss'],baseline_N_B=base['N_B'],baseline_D_B=base['D_B'],
                    loss_gain=base['loss']-best['loss'],
                    reducible_gain_fraction=(base['reducible_loss']-best['reducible_loss'])/base['reducible_loss'])
        return best
