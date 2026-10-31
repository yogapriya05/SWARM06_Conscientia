from backend.lab_core.engine import Engine
from backend.lab_core.models import Config
from backend.lab_core.network import (GROUND, active_links, earliest_route, pair_key,
                                route_candidates)


def test_route_hop_times_and_capacity():
    e=Engine(Config(auto_tasks=False),seed_tasks=False)
    routes=route_candidates(e.state,'S3',10,0,180)
    assert routes
    for r in routes:
        previous=0
        assert r.nodes[0]=='S3' and r.nodes[-1]==GROUND
        assert len(set(r.nodes))==len(r.nodes)
        for h in r.hops:
            assert h.start_s>=previous
            previous=h.start_s+80/h.rate_mbps
            assert previous<=h.end_s
        assert r.arrival_s<=180


def test_removed_nodes_and_blocked_links_are_excluded():
    e=Engine(Config(auto_tasks=False),seed_tasks=False)
    e.inject('S2','offline')
    assert all('S2' not in (l.source,l.target) for l in active_links(e.state))
    e.state.blocked_links.add(pair_key('S1',GROUND))
    r=earliest_route(e.state,'S1',4,0,180)
    assert r
    assert all(pair_key(h.source,h.target)!=pair_key('S1',GROUND) for h in r.hops)


def test_no_gateway_no_delivery_route():
    e=Engine(Config(auto_tasks=False),seed_tasks=False)
    e.inject('S1','radio');e.inject('S4','radio')
    assert earliest_route(e.state,'S3',4,0,180) is None


def test_tiny_deadline_returns_no_route():
    e=Engine(Config(auto_tasks=False),seed_tasks=False)
    assert earliest_route(e.state,'S3',128,0,1) is None
