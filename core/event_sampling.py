"""Служебная выборка событий датчика. Дополнительные каналы наружу не передаются."""
import numpy as np

def select_motion_rows(t,x,payload,travel_index):
    t=np.asarray(t,float);x=np.asarray(x,float);payload=np.asarray(payload,dtype=object)
    if len(t)!=len(x) or payload.ndim!=2 or len(payload)!=len(t):raise ValueError('Несогласованные строки событий')
    if len(t)<2:return np.ones(len(t),dtype=bool),{'other_only_rows':0,'motion_rows':len(t)}
    changed=payload[1:]!=payload[:-1]
    motion=np.not_equal(x[1:],x[:-1])
    other_mask=np.ones(payload.shape[1],dtype=bool);other_mask[travel_index]=False
    other=np.any(changed[:,other_mask],axis=1)
    mask=np.r_[True,motion|~other]
    mask[-1]=True
    moves=np.flatnonzero(motion)+1
    if len(moves) and moves[0]>1:mask[moves[0]-1]=True
    return mask,{'motion_rows':int(motion.sum()),'simultaneous_rows':int(np.sum(motion&other)),
        'other_only_rows':int(np.sum(~motion&other)),'time_only_rows':int(np.sum(~motion&~other)),
        'retained_knots':int(mask.sum())}
