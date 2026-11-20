from datetime import datetime,timedelta
from app.modules.m3_versions.rules import schedule,ZONE
from app.config import RULE_VERSION
from app.errors import DomainError

def minutes(a,b):return int((b-a).total_seconds()//60)

def split_shift(shift):
    if shift['in'] is None or shift['out'] is None:raise DomainError('MISSING','班次缺少进出打卡')
    a=shift['in'];b=shift['out'];start=datetime.fromisoformat(a['at']).astimezone(ZONE);end=datetime.fromisoformat(b['at']).astimezone(ZONE)
    planned_start,planned_end,bs,be=schedule(a)
    if start>=end or end-start>timedelta(hours=18):raise DomainError('RANGE','打卡时长超出18小时')
    if start<planned_start-timedelta(hours=6) or end>planned_end+timedelta(hours=6):raise DomainError('RANGE','打卡超出班次范围')
    if start.second or end.second or start.microsecond or end.microsecond:raise DomainError('RANGE','打卡精度必须为整分钟')
    boundaries={start,end}
    for d in (bs,be,planned_start,planned_end):
        if start<d<end:boundaries.add(d)
    midnight=start.replace(hour=0,minute=0,second=0)+timedelta(days=1)
    while midnight<end:boundaries.add(midnight);midnight+=timedelta(days=1)
    points=sorted(boundaries);segments=[]
    for left,right in zip(points,points[1:]):
        if bs<=left<be:continue
        relation='计划内' if planned_start<=left and right<=planned_end else '加班'
        segments.append({'id':shift['id'],'employee':shift['employee'],'shift_day':shift['day'],'calendar_day':left.date().isoformat(),'start':left.isoformat(),'end':right.isoformat(),'minutes':minutes(left,right),'rate':str(a['hourly_rate']),'line':a['_line'],'relation':relation,'planned_start':planned_start.isoformat(),'planned_end':planned_end.isoformat()})
    attendance={'shift':shift['id'],'employee':shift['employee'],'shift_day':shift['day'],
        'span':minutes(start,end),'break_overlap':max(0,minutes(max(start,bs),min(end,be))),
        'late':max(0,minutes(planned_start,min(start,planned_end))),'early':max(0,minutes(max(end,planned_start),planned_end)),
        'extra':max(0,minutes(start,planned_start))+max(0,minutes(planned_end,end)),
        'planned_span':minutes(planned_start,planned_end),'break':minutes(bs,be),
        'lines':[a['_line'],b['_line']],'window':planned_start.isoformat()+'/'+planned_end.isoformat()}
    return segments,attendance

def apply(state):
    out=[];bad=set();attendance=[];anomalies=[]
    for shift in state['shifts']:
        try:
            segments,att=split_shift(shift)
        except DomainError as e:
            for r in shift['sources']:bad.add(r['_line']);state['quarantine'].append({'line':r['_line'],'id':r['id'],'code':e.code,'raw':r['_raw']})
            continue
        out.extend(segments);attendance.append(att)
        for code,key in (('LATE','late'),('EARLY','early')):
            if att[key]:anomalies.append({'shift':shift['id'],'employee':shift['employee'],'shift_day':shift['day'],'code':code,'minutes':att[key],
                'basis':{'rule':'M4-ATTENDANCE@'+RULE_VERSION,'lines':att['lines'],'window':att['window']},'paired_extra_minutes':att['extra']})
    state['rows']=[r for r in state['rows'] if r['_line'] not in bad]
    state['segments']=out;state['attendance']=attendance;state['anomalies']=anomalies;return state
