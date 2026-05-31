from app.models.audit_event import AuditEvent



def log_event(db, message):
    event = AuditEvent(message=message)

    db.add(event)
    db.commit()
