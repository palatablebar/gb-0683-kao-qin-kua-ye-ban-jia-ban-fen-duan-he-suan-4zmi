from decimal import Decimal
from collections import defaultdict

def attendance_check(state):
    segments=defaultdict(lambda:[0,0])
    for s in state.get('segments',[]):
        segments[s['id']][1 if s.get('relation')=='加班' else 0]+=s['minutes']
    shifts=[];ok=True
    for a in state.get('attendance',[]):
        within,extra=segments.get(a['shift'],[0,0]);worked=within+extra
        span_ok=worked+a['break_overlap']==a['span']
        planned_ok=within+a['late']+a['early']==a['planned_span']-a['break_overlap']
        extra_ok=extra==a['extra']
        ok=ok and span_ok and planned_ok and extra_ok
        shifts.append({'shift':a['shift'],'employee':a['employee'],'worked':worked,'within':within,'extra':extra,
            'late':a['late'],'early':a['early'],'span_ok':span_ok,'planned_ok':planned_ok,'extra_ok':extra_ok,
            'balanced':span_ok and planned_ok and extra_ok})
    return {'shifts':shifts,'balanced':ok}

def money_check(state):
    p=state.get('payable',{});items=p.get('items',[]);anomalies=p.get('anomalies',[]);att=state.get('attendance',[])
    total=sum((Decimal(str(i['amount'])) for i in items),Decimal(0))
    checks={'total_matches':str(total)==str(p.get('total')),
        'anomaly_zero':all(str(a.get('amount'))=='0.00' for a in anomalies),
        'extra_matches_items':sum(i['minutes'] for i in items if i.get('relation')=='加班')==p.get('extra_minutes'),
        'anomaly_matches_items':sum(a['minutes'] for a in anomalies)==p.get('anomaly_minutes'),
        'extra_equals_attendance':p.get('extra_minutes')==sum(a['extra'] for a in att),
        'anomaly_equals_attendance':p.get('anomaly_minutes')==sum(a['late']+a['early'] for a in att)}
    return {'checks':checks,'balanced':all(checks.values())}

def balance(state):
    accepted=len(state['rows']);isolated=len(state['quarantine'])
    accounted=accepted+isolated+state['blank_count']+state['header_count']+state['duplicate_count']
    attendance=attendance_check(state);money=money_check(state)
    count_ok=accounted==state['input_count']
    return {'input':state['input_count'],'accepted':accepted,'isolated':isolated,
        'blank':state['blank_count'],'headers':state['header_count'],'duplicates':state['duplicate_count'],
        'accounted':accounted,'count_ok':count_ok,
        'attendance':attendance,'money':money,
        'balanced':count_ok and attendance['balanced'] and money['balanced'],
        'business':state.get('business',{})}
