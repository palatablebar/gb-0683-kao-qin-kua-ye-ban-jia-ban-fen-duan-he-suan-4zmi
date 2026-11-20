import sqlite3,json,os
from pathlib import Path
from app.errors import DomainError

def connection():
    path=Path(os.environ.get('DB_PATH','data/records.db'));path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=10);db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, body TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, decision TEXT NOT NULL DEFAULT "待复核", status TEXT NOT NULL DEFAULT "有效")')
    if 'status' not in [r[1] for r in db.execute('PRAGMA table_info(runs)')]:
        db.execute("ALTER TABLE runs ADD COLUMN status TEXT NOT NULL DEFAULT '有效'")
    db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    return db

def save(run_id, body):
    # 同一事务内完成取代：任一语句失败即回滚，旧有效结果与原始打卡保留。
    with connection() as db:
        db.execute('INSERT OR IGNORE INTO runs(id,body) VALUES (?,?)',(run_id,json.dumps(body,ensure_ascii=False)))
        db.execute("UPDATE runs SET status='失效' WHERE id!=?",(run_id,))
        db.execute("UPDATE runs SET status='有效' WHERE id=?",(run_id,))
        db.execute("INSERT INTO meta(key,value) VALUES ('latest',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(run_id,))
    return get(run_id)

def get(run_id):
    with connection() as db:r=db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
    if not r:raise DomainError('NOT_FOUND','批次不存在',404)
    body=json.loads(r['body']);body.update(run_id=r['id'],review_version=r['version'],decision=r['decision'],status=r['status']);return body

def history():
    with connection() as db:rows=db.execute("SELECT id,version,decision,status FROM runs ORDER BY CASE WHEN id=(SELECT value FROM meta WHERE key='latest') THEN 0 ELSE 1 END,rowid DESC LIMIT 100").fetchall()
    return [dict(r) for r in rows]

def review(run_id, version, decision):
    if decision not in ('通过','退回'):raise DomainError('DECISION','复核状态无效')
    with connection() as db:
        cur=db.execute('UPDATE runs SET version=version+1,decision=? WHERE id=? AND version=?',(decision,run_id,version))
        if cur.rowcount!=1:
            if not db.execute('SELECT 1 FROM runs WHERE id=?',(run_id,)).fetchone():raise DomainError('NOT_FOUND','批次不存在',404)
            raise DomainError('STALE','复核版本已更新，请刷新',409)
    return get(run_id)
