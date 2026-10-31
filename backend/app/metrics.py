from .models import TERMINAL

def summarize(state):
    counts={k:sum(t.status==k for t in state.tasks.values()) for k in ['pending','deferred','assigned','captured','processed','delivered','expired','failed']}
    for key in ['delivered','expired','failed']:counts[key]+=state.counters['archived_'+key]
    terminal=counts['delivered']+counts['expired']+counts['failed']
    links=__import__(__package__+'.network',fromlist=['build_links']).build_links(state)
    active=[t for t in state.tasks.values() if t.status not in TERMINAL]
    return dict(**counts,total_tasks=len(state.tasks)+state.counters['archived_tasks'],active_tasks=len(active),
        completed_tasks=counts['delivered'],failed_tasks=counts['failed']+counts['expired'],
        completion_pct=100*counts['delivered']/max(1,terminal),
        healthy_nodes=sum(s.health=='healthy' for s in state.satellites.values()),
        available_nodes=sum(s.health!='isolated' for s in state.satellites.values()),
        eclipse_nodes=sum(s.eclipse for s in state.satellites.values()),
        network_availability=sum(l.available for l in links)/max(1,len(links)),
        mean_battery_pct=sum(s.battery_wh for s in state.satellites.values())/len(state.satellites),
        **state.counters)
