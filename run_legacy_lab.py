"""Retained Swarm Lab dashboard including advanced stress controls and original models."""
import argparse
import uvicorn
from backend.lab_core.api import create_app
from backend.lab_core.models import Config
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--nodes',type=int,default=6,choices=range(3,41));p.add_argument('--port',type=int,default=8001);a=p.parse_args()
    uvicorn.run(create_app(Config(nodes=a.nodes)),host='127.0.0.1',port=a.port)
