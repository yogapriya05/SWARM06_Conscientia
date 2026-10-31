"""Earth-centred J2 dynamics, annual Sun geometry, body attitude and eclipses.

ECI axis convention: x=reference equinox, y=north pole, z=east equatorial.
This is an axis permutation of the conventional z-pole ECI frame, for Three.js.
"""
import math
import numpy as np
EARTH_KM=6371.0
GRAVITY_RADIUS_KM=6378.137
MU=398600.4418
J2=1.08262668e-3
OMEGA_EARTH=2*math.pi/86164.0905
YEAR_S=365.256363004*86400
OBLIQUITY=math.radians(23.43928)
SOLAR_FLUX_W_M2=1361.0
GROUND_LAT=18.52;GROUND_LON=73.86

def sun_direction(now):
    # Circular Earth revolution; epoch phase is a chosen vernal-equinox reference.
    # Parallel rays, fixed irradiance; solar gravity and inverse-square modulation omitted by request.
    angle=2*math.pi*now/YEAR_S
    return np.array([math.cos(angle),math.sin(angle)*math.sin(OBLIQUITY),math.sin(angle)*math.cos(OBLIQUITY)])
SUN=sun_direction(0)

def earth_point(lat,lon,now,radius=EARTH_KM):
    a,b=math.radians(lat),math.radians(lon)+OMEGA_EARTH*now
    return np.array([radius*math.cos(a)*math.cos(b),radius*math.sin(a),radius*math.cos(a)*math.sin(b)])

def initial_state(index,count,spacing_km=50.):
    radius=EARTH_KM+550.;inc=math.radians(51.6)
    u0=math.asin(math.sin(math.radians(GROUND_LAT))/math.sin(inc))
    raan=math.radians(GROUND_LON)-math.atan2(math.sin(u0)*math.cos(inc),math.cos(u0))
    step=2*math.asin(spacing_km/(2*radius))  # Exactly 50 km Euclidean chord at epoch.
    u=u0+(index-(count-1)/2)*step
    n=math.sqrt(MU/radius**3)
    p=radius*np.array([math.cos(u),math.sin(u)*math.sin(inc),math.sin(u)*math.cos(inc)])
    v=radius*n*np.array([-math.sin(u),math.cos(u)*math.sin(inc),math.cos(u)*math.cos(inc)])
    c,s=math.cos(raan),math.sin(raan);rot=np.array([[c,0,-s],[0,1,0],[s,0,c]])
    return rot@p,rot@v

def acceleration(position,j2=J2):
    r=np.asarray(position,dtype=float);r2=np.sum(r*r,axis=-1,keepdims=True);rn=np.sqrt(r2)
    base=-MU*r/(r2*rn)
    q=5*r[...,1:2]**2/r2
    factors=np.concatenate([q-1,q-3,q-1],axis=-1)
    return base+1.5*j2*MU*GRAVITY_RADIUS_KM**2*r*factors/(r2*r2*rn)

def rk4(r,v,dt):
    a1=acceleration(r);r2=r+.5*dt*v;v2=v+.5*dt*a1
    a2=acceleration(r2);r3=r+.5*dt*v2;v3=v+.5*dt*a2
    a3=acceleration(r3);r4=r+dt*v3;v4=v+dt*a3;a4=acceleration(r4)
    return r+dt*(v+2*v2+2*v3+v4)/6,v+dt*(a1+2*a2+2*a3+a4)/6

def orbit(sat,now,per_swarm):
    """Compatibility helper: coherent initial orbit, with short circular prediction."""
    p,v=initial_state(sat.index,max(per_swarm*(2 if sat.swarm=='SWARM-02' else 1),sat.index+1))
    radius=np.linalg.norm(p);n=math.sqrt(MU/radius**3)
    return p*math.cos(n*now)+v/n*math.sin(n*now),v*math.cos(n*now)-p*n*math.sin(n*now)

def predicted_position(sat,dt):
    r=np.array(sat.position);v=np.array(sat.velocity);n=math.sqrt(MU/float(np.linalg.norm(r))**3)
    return r*math.cos(n*dt)+v/n*math.sin(n*dt)

def is_eclipsed(position,sun):
    projection=float(np.dot(position,sun))
    return bool(projection<0 and np.dot(position,position)-projection**2<EARTH_KM**2)

def body_axes(sat):
    r=np.asarray(sat.position);v=np.asarray(sat.velocity)
    outward=r/np.linalg.norm(r);forward=v-outward*np.dot(v,outward);forward/=np.linalg.norm(forward)
    cross=np.cross(outward,forward);cross/=np.linalg.norm(cross)
    # Coupled attitude changes rotate both camera/body and all mounted antenna normals.
    yaw=math.radians(sat.attitude_error_deg+sat.body_yaw_deg)
    roll=math.radians(sat.body_roll_deg)
    x=forward*math.cos(yaw)+cross*math.sin(yaw)
    y=-forward*math.sin(yaw)+cross*math.cos(yaw)
    y2=y*math.cos(roll)+outward*math.sin(roll);z=-y*math.sin(roll)+outward*math.cos(roll)
    return np.column_stack([x,y2,z])

def update_positions(state):
    sats=list(state.satellites.values());n=len(sats)
    if not hasattr(state,'_rv_time'):
        pairs=[initial_state(s.index,n,state.config.spacing_km) for s in sats]
        state._r=np.array([x[0] for x in pairs]);state._v=np.array([x[1] for x in pairs]);state._rv_time=0.
    remaining=state.time_s-state._rv_time
    while remaining>1e-9:
        dt=min(5.,remaining);state._r,state._v=rk4(state._r,state._v,dt);remaining-=dt
    state._rv_time=state.time_s;sun=sun_direction(state.time_s)
    for sat,p,v in zip(sats,state._r,state._v):
        sat.position=p.tolist();sat.velocity=v.tolist();sat.eclipse=is_eclipsed(p,sun)
        sat.body_roll_deg=3.*math.sin(state.time_s/95+sat.index*.43)
        axes=body_axes(sat);sat.body_axes_eci=axes.tolist()
        # Two-sided solar wings (+/- body Y), basic projected area and fixed far-field flux.
        incidence=abs(float(axes[:,1]@sun));sat.solar_incidence=incidence
        sat.solar_flux_w_m2=0. if sat.eclipse else SOLAR_FLUX_W_M2
        sat.solar_w=sat.solar_flux_w_m2*.14*.28*max(.08,incidence)
        # Lumped absorbed direct solar heat; small exposed area, no convection.
        body_inc=.5*abs(float(axes[:,0]@sun))+.3*abs(float(axes[:,1]@sun))+.2*abs(float(axes[:,2]@sun))
        sat.solar_heat_w=sat.solar_flux_w_m2*.018*.6*body_inc

def line_of_sight(a,b):
    d=[b[i]-a[i] for i in range(3)];d2=sum(x*x for x in d)
    k=max(0.,min(1.,-sum(a[i]*d[i] for i in range(3))/max(1e-12,d2)))
    return bool(sum((a[i]+k*d[i])**2 for i in range(3))>=(EARTH_KM-.001)**2)

def visibility_windows(state,start,end):
    windows={}
    for sat in state.satellites.values():
        phase=(sat.index*7)%110;windows[sat.id]=[]
        for k in range(math.floor((start-phase)/110)-1,math.ceil((end-phase)/110)+1):
            a,b=max(start,phase+110*k),min(end,phase+110*k+85)
            if b>a:windows[sat.id].append([a,b])
    return windows
