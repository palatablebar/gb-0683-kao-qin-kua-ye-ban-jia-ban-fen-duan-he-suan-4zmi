from datetime import date
from decimal import Decimal,ROUND_HALF_UP
from collections import defaultdict
from app.config import RULE_VERSION

ADJUDICATION='迟到早退属纪律责任，加班属报酬责任；同一班次两笔责任并列进入本可付款结果，互不抵减，异常行金额恒为0.00，加班按实际日历日倍率计酬。'

def price(segments,holidays):
    normal_used=defaultdict(int);out=[]
    for s in sorted(segments,key=lambda r:(r['start'],r['employee'])):
        d=date.fromisoformat(s['calendar_day']);key=(s['employee'],s['calendar_day']);minutes=s['minutes'];rate=Decimal(str(s['rate']))
        if s['calendar_day'] in holidays:parts=[(minutes,Decimal(3),'HOLIDAY')]
        elif d.weekday()>=5:parts=[(minutes,Decimal(2),'REST')]
        else:
            regular=min(minutes,max(0,480-normal_used[key]));normal_used[key]+=minutes
            parts=[(regular,Decimal(1),'REGULAR'),(minutes-regular,Decimal('1.5'),'OVERTIME')]
        for count,multiplier,code in parts:
            if count:
                item=dict(s);item.update(minutes=count,multiplier=str(multiplier),code=code,amount=str((rate*count*multiplier/60).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)))
                item['basis']={'rule':'M5-PRICE@'+RULE_VERSION,'shift':s['id'],'lines':[s['line']],'relation':s.get('relation','计划内'),'window':str(s.get('planned_start',''))+'/'+str(s.get('planned_end',''))}
                out.append(item)
    return out

def apply(state):
    holidays=set(state['parameters'].get('holidays',['2026-10-01']))
    calculations=price(state['segments'],holidays)
    anomalies=[]
    for a in state.get('anomalies',[]):
        item=dict(a);item['amount']='0.00';item['note']='纪律责任，不抵减加班';anomalies.append(item)
    anomaly_by_shift=defaultdict(int)
    for a in anomalies:anomaly_by_shift[a['shift']]+=a['minutes']
    for c in calculations:
        if c.get('relation')=='加班' and anomaly_by_shift.get(c['id']):c['basis']['paired_anomaly_minutes']=anomaly_by_shift[c['id']]
    total=sum((Decimal(r['amount']) for r in calculations),Decimal(0));paid=sum((Decimal(str(r['paid'])) for r in state['rows']),Decimal(0))
    extra_minutes=sum(c['minutes'] for c in calculations if c.get('relation')=='加班');anomaly_minutes=sum(a['minutes'] for a in anomalies)
    state['calculations']=calculations
    state['payable']={'ruling':'SEPARATE_NO_NETTING','adjudication':ADJUDICATION,'rule_version':RULE_VERSION,
        'items':calculations,'anomalies':anomalies,'total':str(total),
        'extra_minutes':extra_minutes,'anomaly_minutes':anomaly_minutes,'unit':'CNY'}
    state['business']={'total':str(total),'paid':str(paid),'difference':str(total-paid),'minutes':sum(r['minutes'] for r in calculations),
        'extra_minutes':extra_minutes,'anomaly_minutes':anomaly_minutes,'unit':'CNY'}
    return state
