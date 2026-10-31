"""Coarse mounted-patch model: body-frame rays, slab occlusion, cone and gain.

Not an EM solver: a 10x10x30 cm box and three patch antenna mounts. Geometry
is evaluated at both endpoints. An edge exists only when a usable pair exists.
"""
import math
import numpy as np
HALF_SIZE_M=np.array([.05,.05,.15])

def ray_hits_body(origin,direction):
    low,high=-math.inf,math.inf
    for o,d,h in zip(origin,direction,HALF_SIZE_M):
        if abs(d)<1e-12:
            if abs(o)>h:return False
            continue
        a,b=(-h-o)/d,(h-o)/d;low=max(low,min(a,b));high=min(high,max(a,b))
        if high<low:return False
    return bool(high>=max(low,1e-6))

def evaluate(sat,target_position,ground=False):
    axes=sat.body_axes_eci
    if len(axes)!=3:return dict(gain=0.,angle_deg=180.,body_blocked=True,clear=False,antenna='none')
    d=[target_position[k]-sat.position[k] for k in range(3)];norm=math.sqrt(sum(x*x for x in d))
    if norm<1e-9:return dict(gain=0.,angle_deg=180.,body_blocked=True,clear=False,antenna='coincident')
    direction=[sum(axes[j][i]*d[j] for j in range(3))/norm for i in range(3)]
    tilt=math.radians(sat.antenna_mount_deg+sat.antenna_error_deg);c,s=math.cos(tilt),math.sin(tilt)
    mounts=[('fore',(.055,0,0),(c,0,-s)),('aft',(-.055,0,0),(-c,0,s))]
    if ground:mounts.append(('nadir',(0,0,-.155),(-s,0,-c)))
    candidates=[]
    for name,origin,boresight in mounts:
        dot=max(-1.,min(1.,sum(n*x for n,x in zip(boresight,direction))));angle=math.degrees(math.acos(dot))
        blocked=ray_hits_body(origin,direction);clear=not blocked and angle<=sat.antenna_beam_half_deg
        candidates.append(dict(gain=max(0.,dot)**4 if clear else 0.,angle_deg=angle,body_blocked=blocked,clear=clear,antenna=name))
    good=[x for x in candidates if x['clear']]
    return max(good,key=lambda x:x['gain']) if good else min(candidates,key=lambda x:x['angle_deg'])
