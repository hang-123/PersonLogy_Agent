import asyncio, sys
from pathlib import Path
sys.path.insert(0, "D:/PersonLogy_Agent/packages/personlogy_core/src")
from personlogy.adapters.sqlite_audit import SQLiteRecordStore
from personlogy.domain.audit import AuditEvent, digest_for

async def main():
    p = "D:/PersonLogy_Agent/.tmp/smoke.sqlite3"
    try: Path(p).unlink()
    except FileNotFoundError: pass
    store = SQLiteRecordStore(p)
    await store.append(AuditEvent(event_type="job.succeeded", status="succeeded",
        trace_id="t1", actor_type="system", entity_type="job", entity_id="j1"))
    await store.append(AuditEvent(event_type="job.failed", status="failed",
        trace_id="t1", actor_type="system", entity_type="job", entity_id="j2",
        before_digest=digest_for({"s":"running"}), after_digest=digest_for({"s":"failed"})))
    print("verify_chain:", await store.verify_chain())
    # tamper
    con = store.connect()
    con.execute("UPDATE audit_event SET status='tampered' WHERE sequence=1")
    con.commit(); con.close()
    print("after tamper:", await store.verify_chain())

asyncio.run(main())
