"""Circular two-body visualization; observation/ground windows are explicit demo inputs."""
import math
import numpy as np
EARTH_KM = 6371.0
MU = 398600.4418
OMEGA_EARTH = 2*math.pi/86164.0
SUN = np.array([1., .14, .08]); SUN /= np.linalg.norm(SUN)
GROUND_LAT = 18.52
GROUND_LON = 73.86

def earth_point(lat, lon, now, radius=EARTH_KM):
    a,b = math.radians(lat), math.radians(lon)+OMEGA_EARTH*now
    return np.array([radius*math.cos(a)*math.cos(b),radius*math.sin(a),radius*math.cos(a)*math.sin(b)])

def orbit(sat, now, per_swarm):
    radius = EARTH_KM+550+(100 if sat.swarm=='SWARM-02' else 0)
    inclination = math.radians(51.6 if sat.swarm=='SWARM-01' else 74.)
    raan = 0. if sat.swarm=='SWARM-01' else math.radians(80)
    n = math.sqrt(MU/radius**3)
    u = 2*math.pi*sat.slot/per_swarm+n*now+(0 if sat.swarm=='SWARM-01' else .35)
    p = np.array([math.cos(u),math.sin(u)*math.sin(inclination),math.sin(u)*math.cos(inclination)])
    v = n*radius*np.array([-math.sin(u),math.cos(u)*math.sin(inclination),math.cos(u)*math.cos(inclination)])
    rot = np.array([[math.cos(raan),0,-math.sin(raan)],[0,1,0],[math.sin(raan),0,math.cos(raan)]])
    return rot@(p*radius), rot@v

def update_positions(state):
    for sat in state.satellites.values():
        p,v=orbit(sat,state.time_s,state.config.satellites_per_swarm)
        sat.position, sat.velocity=p.tolist(),v.tolist()
        behind = float(p@SUN)<0
        sat.eclipse=bool(behind and np.linalg.norm(p-float(p@SUN)*SUN)<EARTH_KM)
        sat.solar_w=0. if sat.eclipse else 46.*max(.12,1-sat.attitude_error_deg/100)

def line_of_sight(a,b):
    a,b=np.array(a),np.array(b); d=b-a
    k=float(np.clip(-(a@d)/max(1e-12,d@d),0,1))
    return float(np.linalg.norm(a+k*d))>=EARTH_KM-1

def visibility_windows(state,start,end):
    # Synthetic, satellite-specific repeating windows, independent of radio topology.
    windows={}
    for sat in state.satellites.values():
        phase=(sat.slot*17+(0 if sat.swarm=='SWARM-01' else 29))%110
        windows[sat.id]=[]
        for k in range(math.floor((start-phase)/110)-1,math.ceil((end-phase)/110)+1):
            a,b=max(start,phase+110*k),min(end,phase+110*k+72)
            if b>a:windows[sat.id].append([a,b])
    return windows
