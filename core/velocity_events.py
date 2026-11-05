"""Оценка скорости по четырём событиям только при обнаруженном периоде 4."""
import numpy as np
from scipy.signal import savgol_filter

def period4(t,x):
    change=np.r_[True,np.diff(x)!=0];te=np.asarray(t,float)[change];xe=np.asarray(x,float)[change]
    info={'detected':False,'reason':'Недостаточно событий'}
    if len(te)<80:return info,te,xe
    dx=np.diff(xe);sign=np.sign(dx);edges=np.r_[0,np.flatnonzero(np.diff(sign)!=0)+1,len(sign)]
    lo,hi=max(zip(edges[:-1],edges[1:]),key=lambda pair:pair[1]-pair[0])
    n=hi-lo
    if n<60:return info,te,xe
    left=lo+n//5;right=hi-n//5;steps=np.abs(dx[left:right]);q=float(np.median(steps))
    if q<=0 or np.mean(np.isclose(steps,q,rtol=1e-4,atol=1e-9))<.95:
        return {'detected':False,'reason':'Нет устойчивого кванта положения'},te,xe
    dt=np.diff(te)[left:right]
    if np.any(dt<=0):return {'detected':False,'reason':'Не возрастающее время событий'},te,xe
    w=min(51,len(dt) if len(dt)%2 else len(dt)-1)
    residual=dt-savgol_filter(dt,w,2)
    if np.std(residual)<1e-7:return {'detected':False,'reason':'Нет выраженной периодической неравномерности'},te,xe
    a2=float(np.corrcoef(residual[:-2],residual[2:])[0,1]);a4=float(np.corrcoef(residual[:-4],residual[4:])[0,1])
    detected=bool(np.isfinite([a2,a4]).all() and a4>.85 and a2<-.5)
    return {'detected':detected,'quantum_mm':q,'lag2':a2,'lag4':a4,
            'reason':'Обнаружено чередование интервалов с периодом 4' if detected else 'Период 4 не подтверждён'},te,xe

def corrected_process(d,config):
    step=float(config['dt']);n=int(np.floor(d['t'][-1]/step))+1
    if not 5<=n<=1000000:raise ValueError('Неподходящая длительность записи')
    u=np.arange(n)*step;knots=d.get('motion_t',d['t']);values=d.get('motion_x',d['x'])
    raw=np.interp(u,knots,values);w=min(15,n if n%2 else n-1);x=savgol_filter(raw,w,3)
    if d.get('sampling_mode')!='pkv_events':
        return {'t':u,'x':x,'v':savgol_filter(raw,w,3,deriv=1,delta=step),'velocity_method':'sampled_savgol'}
    info,te,xe=period4(knots,values)
    if not info['detected']:
        return {'t':u,'x':x,'v':savgol_filter(raw,w,3,deriv=1,delta=step),'velocity_method':'event_savgol','velocity_quality':info}
    i=np.arange(2,len(te)-2)
    velocity=(xe[i+2]-xe[i-2])/(te[i+2]-te[i-2])
    v=np.interp(u,te[i],velocity,left=0.,right=0.)
    fallback=savgol_filter(raw,w,3,deriv=1,delta=step)
    edge=(u<te[i[0]])|(u>te[i[-1]])
    v[edge]=fallback[edge]
    info['edge_unresolved_ms']=[[float(u[0]),float(te[i[0]])],[float(te[i[-1]]),float(u[-1])]]
    info['median_velocity_support_ms']=float(np.median(te[i+2]-te[i-2]))
    return {'t':u,'x':x,'v':v,'velocity_method':'event_central_four_intervals','velocity_quality':info}
