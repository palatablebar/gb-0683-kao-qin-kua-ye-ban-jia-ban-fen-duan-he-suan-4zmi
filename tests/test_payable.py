from copy import deepcopy
from decimal import Decimal
import pytest
from app.workflow import run,load
from app.modules.m6_reconcile.compare import balance
from app import store

@pytest.fixture
def ot():return run(load('overtime.csv'),{})

def test_late_and_extra_coexist_no_netting(ot):
    # 裁决：晚到30分钟与多留90分钟同班并列，互不抵减
    anomalies=[a for a in ot['payable']['anomalies'] if a['employee']=='E102']
    assert len(anomalies)==1 and anomalies[0]['code']=='LATE' and anomalies[0]['minutes']==30
    extra=[c for c in ot['calculations'] if c['employee']=='E102' and c['relation']=='加班']
    assert sum(c['minutes'] for c in extra)==90
    total=sum(Decimal(c['amount']) for c in ot['calculations'] if c['employee']=='E102')
    assert total==Decimal('220.00')

def test_anomaly_amount_always_zero(ot):
    assert ot['payable']['anomalies'] and all(a['amount']=='0.00' for a in ot['payable']['anomalies'])
    assert sum(Decimal(a['amount']) for a in ot['payable']['anomalies'])==0

def test_early_leave_kept_as_discipline(ot):
    early=[a for a in ot['payable']['anomalies'] if a['employee']=='E103']
    assert len(early)==1 and early[0]['code']=='EARLY' and early[0]['minutes']==60
    assert not [c for c in ot['calculations'] if c['employee']=='E103' and c['relation']=='加班']

def test_card_supplement_replaces_old_judgement(ot):
    # 补卡(version=2)采信后，旧的早退判定消失，只认多留60分钟
    assert not [a for a in ot['payable']['anomalies'] if a['employee']=='E104']
    extra=[c for c in ot['calculations'] if c['employee']=='E104' and c['relation']=='加班']
    assert sum(c['minutes'] for c in extra)==60

def test_payable_totals(ot):
    assert ot['payable']['total']=='880.00' and ot['payable']['extra_minutes']==150 and ot['payable']['anomaly_minutes']==90
    assert ot['payable']['ruling']=='SEPARATE_NO_NETTING' and ot['payable']['adjudication']

def test_basis_traceable(ot):
    anomaly=[a for a in ot['payable']['anomalies'] if a['employee']=='E102'][0]
    assert anomaly['basis']['lines']==[4,5] and 'M4-ATTENDANCE' in anomaly['basis']['rule'] and anomaly['paired_extra_minutes']==90
    extra=[c for c in ot['calculations'] if c['employee']=='E102' and c['relation']=='加班'][0]
    assert extra['basis']['paired_anomaly_minutes']==30 and extra['basis']['lines']==[4] and 'M5-PRICE' in extra['basis']['rule']
    assert extra['basis']['window']==anomaly['basis']['window']

def test_reconcile_attendance_identities(ot):
    attendance=ot['reconcile']['attendance']
    assert attendance['balanced'] and all(s['balanced'] for s in attendance['shifts'])
    e102=[s for s in attendance['shifts'] if s['employee']=='E102'][0]
    assert (e102['within'],e102['extra'],e102['late'],e102['early'])==(390,90,30,0)

def test_reconcile_money_checks(ot):
    assert all(ot['reconcile']['money']['checks'].values()) and ot['reconcile']['balanced']

def test_tampered_anomaly_breaks_balance(ot):
    s=deepcopy(ot);s['payable']['anomalies'][0]['minutes']=999
    assert balance(s)['balanced'] is False

def test_tampered_extra_breaks_balance(ot):
    s=deepcopy(ot);s['attendance'][1]['extra']=1
    assert balance(s)['balanced'] is False

def test_netting_would_break_balance(ot):
    # 若把异常与加班净额结算（异常行承担金额），金额守恒立即失败
    s=deepcopy(ot);s['payable']['anomalies'][0]['amount']='-10.00'
    assert balance(s)['money']['checks']['anomaly_zero'] is False and balance(s)['balanced'] is False

def test_same_credentials_same_run_id():
    assert run(load('overtime.csv'),{})['run_id']==run(load('overtime.csv'),{})['run_id']

def test_approval_change_new_run_id():
    assert run(load('overtime.csv'),{})['run_id']!=run(load('overtime.csv'),{'holidays':['2026-10-01','2026-10-02']})['run_id']

def test_supersede_and_keep_old(ot,tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'r.db'))
    dirty=run(load('dirty.csv'),{})
    store.save(dirty['run_id'],dirty);store.save(ot['run_id'],ot)
    history={h['id']:h['status'] for h in store.history()}
    assert history[ot['run_id']]=='有效' and history[dirty['run_id']]=='失效'
    old=store.get(dirty['run_id'])
    assert old['status']=='失效' and old['calculations']==dirty['calculations'] and old['source_b64']

def test_rerun_same_credentials_no_duplicate(ot,tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'r.db'))
    store.save(ot['run_id'],ot);store.save(ot['run_id'],ot)
    assert len(store.history())==1 and store.history()[0]['status']=='有效'

def test_failed_replacement_keeps_old_payable(ot,tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'r.db'))
    store.save(ot['run_id'],ot)
    from app.errors import DomainError
    with pytest.raises(DomainError):run(b'wrong\n1\n',{})
    assert store.history()[0]['id']==ot['run_id'] and store.get(ot['run_id'])['status']=='有效'

def test_export_has_ruling_and_anomaly_rows(ot):
    import csv,io
    from app.modules.m7_archive.export_out import bundle
    rows=list(csv.reader(io.StringIO(bundle(ot).lstrip('﻿'))))
    kinds=[r[0] for r in rows]
    assert '裁决' in kinds and kinds.count('异常')==len(ot['payable']['anomalies'])
    assert 'SEPARATE_NO_NETTING' in rows[kinds.index('裁决')][5]

def test_export_superseded_rejected(client):
    a=client.post('/api/runs',json={'sample':'dirty.csv'}).get_json()
    client.post('/api/runs',json={'sample':'overtime.csv'})
    r=client.get('/api/archive/'+a['run_id']+'/export.csv')
    assert r.status_code==409 and r.get_json()['code']=='SUPERSEDED'

def test_export_current_payable_only(client):
    s=client.post('/api/runs',json={'sample':'overtime.csv'}).get_json()
    r=client.get('/api/archive/'+s['run_id']+'/export.csv')
    assert r.status_code==200 and '裁决' in r.data.decode('utf-8-sig')

def test_seal_rechecks_balance_not_stored_flag(client,tmp_path,monkeypatch):
    # 封存时重新对账：即使库内标记被改成平衡，篡改的异常金额也不能封存
    s=client.post('/api/runs',json={'sample':'overtime.csv'}).get_json()
    from app import store
    st=store.get(s['run_id']);st['payable']['anomalies'][0]['amount']='-10.00';st['reconcile']['balanced']=True
    import sqlite3,json,os
    db=sqlite3.connect(os.environ['DB_PATH']);db.execute('UPDATE runs SET body=? WHERE id=?',(json.dumps(st,ensure_ascii=False),s['run_id']));db.commit();db.close()
    r=client.get('/api/archive/'+s['run_id']+'/export.csv')
    assert r.status_code==422 and r.get_json()['code']=='UNBALANCED'

def test_page_presents_payable_result(client):
    client.post('/api/runs',json={'sample':'overtime.csv'})
    page=client.get('/m5_calculate')
    assert page.status_code==200 and '班次异常' in page.data.decode() and '迟到' in page.data.decode()
