"""Run from this directory: python run.py. No Node runtime needed for bundled UI."""
import argparse,json
from pathlib import Path
from backend.app.models import Config

def main():
    p=argparse.ArgumentParser(description='3D disaster observation-and-delivery swarm')
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8000)
    p.add_argument('--swarms',type=int,choices=[1,2],default=2);p.add_argument('--satellites',type=int,choices=range(1,21),default=6)
    p.add_argument('--seed',type=int,default=7);p.add_argument('--headless',action='store_true');p.add_argument('--seconds',type=int,default=300)
    p.add_argument('--space-effects',action='store_true');p.add_argument('--export',type=Path)
    a=p.parse_args();config=Config(swarm_count=a.swarms,satellites_per_swarm=a.satellites,seed=a.seed,space_effects=a.space_effects)
    if a.headless:
        from backend.app.engine import Engine
        e=Engine(config)
        for _ in range(a.seconds):e.step(emit_snapshot=False);e.validate()
        print(json.dumps(e.snapshot()['metrics'],indent=2))
        if a.export:a.export.write_text(json.dumps(e.snapshot(),indent=2),encoding='utf-8')
    else:
        import uvicorn
        from backend.app.api import create_app
        print(f'Open http://{a.host}:{a.port} · starts paused')
        uvicorn.run(create_app(config),host=a.host,port=a.port,workers=1)
if __name__=='__main__':main()
