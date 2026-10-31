from pydantic import BaseModel,Field,ConfigDict,model_validator
from typing import Literal

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class ConfigRequest(Strict):
    swarm_count:Literal[1,2]=2
    satellites_per_swarm:int=Field(6,ge=1,le=20)
    seed:int=Field(7,ge=0,le=2**31-1)
    speed:float=Field(1,ge=1,le=100)
    auto_tasks:bool=True
    space_effects:bool=False
    random_revival:bool=True
    exaggerated_effects:bool=True
class Settings(Strict):
    speed:float|None=Field(None,ge=1,le=100)
    auto_tasks:bool|None=None
    space_effects:bool|None=None
    random_revival:bool|None=None
    exaggerated_effects:bool|None=None
class Target(Strict):
    lat:float=Field(18.52,ge=-90,le=90)
    lon:float=Field(73.86,ge=-180,le=180)
class TaskRequest(Strict):
    task_id:str|None=Field(None,max_length=64)
    event_id:str|None=Field(None,max_length=64)
    target:Target=Field(default_factory=Target)
    observation_window:list[float]|None=Field(None,min_length=2,max_length=2)
    delivery_deadline:float|None=None
    priority:int=Field(4,ge=1,le=5)
    capture_duration_s:float=Field(5,ge=.5,le=60)
    processing_cycles:float=Field(8_000_000,ge=1,le=1e10)
    raw_data_mb:float=Field(40,ge=.1,le=256)
    output_data_mb:float=Field(10,ge=.1,le=128)
    minimum_quality:float=Field(.8,ge=0,le=1)
    required_captures:int=Field(1,ge=1,le=5)
    cpu_demand:float=Field(35,ge=5,le=75)
    name:str=Field('Fire observation',min_length=1,max_length=100)
    kind:Literal['gnss','remote_sensing']='remote_sensing'
    allowed_satellites:list[str]|None=None
    @model_validator(mode='after')
    def order(self):
        if self.observation_window and self.observation_window[0]>=self.observation_window[1]:raise ValueError('Window must increase')
        return self
class Fault(Strict):
    node_id:str|None=None
    satellite_id:str|None=None
    swarm_id:Literal['SWARM-01','SWARM-02']|None=None
    kind:str='offline'
    failure_mode:str|None=None
    duration_s:float|None=Field(None,gt=0,le=3600)
    duration_ticks:int|None=Field(None,ge=1,le=3600)
    reason:str='operator injection'
class Recovery(Strict):
    node_id:str
    restore_resources:bool=True
class Battery(Strict):
    node_id:str
    percent:float=Field(ge=0,le=100)
class Stress(Strict):
    node_id:str
    cpu_pct:float=Field(0,ge=0,le=100)
    heat_w:float=Field(0,ge=0,le=120)
    drain_w:float=Field(0,ge=0,le=500)
    cooling_scale:float=Field(1,ge=.1,le=2)
class Control(Strict):
    action:Literal['run','pause','step']
    ticks:int=Field(1,ge=1,le=300)
class Step(Strict):
    ticks:int=Field(1,ge=1,le=300)
    seconds:float|None=Field(None,gt=0,le=300)
class LinkRequest(Strict):
    source:str
    target:str
    blocked:bool=True
    duration_s:float|None=Field(None,gt=0,le=3600)
class Priority(Strict):
    event_id:str
    priority:int=Field(ge=1,le=5)
