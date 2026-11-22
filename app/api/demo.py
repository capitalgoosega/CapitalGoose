"""
Demo: a pretend contractor-software app ("BuildRight") that embeds the Capital Goose
widget, so the whole flow can be shown from the front end.

OFF unless DEMO_ENABLED=true. It only ever uses a SANDBOX partner (practice data; lender
emails go to TEST_RECIPIENT_EMAIL or are suppressed), and its helper endpoints only touch
that partner's referrals. Turn it off after the demo by removing DEMO_ENABLED.
"""
import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine import statuses as S
from app.engine.handoff_service import document_summary
from app.engine.lender_links import hash_link_token
from app.engine.ratelimit import SlidingWindowLimiter
from app.engine.referral_service import InvalidTransition, record_status, serialize_referral
from app.engine.security import generate_api_key
from app.models.partner import Partner, Referral, WidgetSession

router = APIRouter()
DEMO_PARTNER = "Demo: BuildRight Contractor Software"
_limiter = SlidingWindowLimiter(limit=40, window_seconds=60)


def _base():
    return os.environ.get("APP_BASE_URL", "https://capitalgoose-production.up.railway.app").rstrip("/")


def _enabled():
    if os.environ.get("DEMO_ENABLED", "").strip().lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")


def _partner(db):
    p = db.query(Partner).filter(Partner.name == DEMO_PARTNER).first()
    if not p:
        _, prefix, key_hash = generate_api_key("sandbox")   # the key itself is never needed or shown
        p = Partner(name=DEMO_PARTNER, mode="sandbox", api_key_prefix=prefix, api_key_hash=key_hash)
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


def _own(db, public_id):
    p = _partner(db)
    ref = db.query(Referral).filter(Referral.public_id == public_id, Referral.partner_id == p.id).first()
    if not ref:
        raise HTTPException(status_code=404, detail="Referral not found")
    return ref


def _ip(request: Request):
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


@router.post("/session")
def demo_session(request: Request, db: Session = Depends(get_db)):
    _enabled()
    if not _limiter.allow(_ip(request)):
        raise HTTPException(status_code=429, detail="Slow down")
    import secrets
    p = _partner(db)
    token = secrets.token_urlsafe(32)
    db.add(WidgetSession(
        partner_id=p.id, token_hash=hash_link_token(token), external_ref="demo-buildright",
        allowed_origin=_base(),
        prefill_json=json.dumps({"first_name": "Dana", "last_name": "Whitfield", "email": "dana@buildright-demo.example",
                                 "legal_name": "Whitfield Roofing LLC", "state": "GA", "years_in_business": "6",
                                 "annual_revenue": "900000", "loan_amount": "250000", "loan_type": "sba_7a"}),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    ))
    db.commit()
    return {"token": token, "script_url": f"{_base()}/widget/embed.js"}


@router.get("/referral/{public_id}")
def demo_referral(public_id: str, db: Session = Depends(get_db)):
    _enabled()
    ref = _own(db, public_id)
    body = serialize_referral(db, ref)
    body["documents"] = document_summary(db, ref)
    body["actions"] = [s for s in (S.LENDER_RECEIVED, S.APPROVED, S.CLOSING, S.FUNDED) if S.can_transition(ref.status, s)] \
        if ref.status in S.FORWARD_PATH and S.FORWARD_PATH.index(ref.status) >= S.FORWARD_PATH.index(S.SUBMITTED) else []
    return body


class LenderAction(BaseModel):
    status: str


@router.post("/referral/{public_id}/lender")
def demo_lender_action(public_id: str, payload: LenderAction, db: Session = Depends(get_db)):
    """Plays the lender pressing a button on their status link."""
    _enabled()
    ref = _own(db, public_id)
    if payload.status not in (S.LENDER_RECEIVED, S.APPROVED, S.CLOSING, S.FUNDED):
        raise HTTPException(status_code=422, detail="Unsupported demo action")
    try:
        record_status(db, ref, payload.status, detail="demo: lender action", source="lender")
    except InvalidTransition as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"status": ref.status}


@router.get("", response_class=HTMLResponse)
def demo_page():
    _enabled()
    return HTMLResponse(_PAGE, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BuildRight (demo) - powered by Capital Goose</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:system-ui,Segoe UI,sans-serif;color:#0f172a;background:#f1f5f9}
.top{background:#1e293b;color:#fff;padding:10px 20px;display:flex;justify-content:space-between;align-items:center}
.top b{font-size:18px}.top span{font-size:12px;opacity:.8}
.banner{background:#fef3c7;color:#78350f;font-size:13px;padding:6px 20px;border-bottom:1px solid #fcd34d}
.wrap{display:grid;grid-template-columns:200px 1fr 380px;gap:16px;padding:16px;max-width:1500px;margin:0 auto}
nav a{display:block;padding:9px 12px;border-radius:8px;color:#334155;text-decoration:none;font-size:14px}
nav a.on{background:#fff;font-weight:600;box-shadow:0 1px 2px #0002}
.card{background:#fff;border-radius:12px;padding:16px;box-shadow:0 1px 3px #0001}
.kpis{display:flex;gap:12px;margin-bottom:14px}.kpi{flex:1;background:#fff;border-radius:12px;padding:12px;box-shadow:0 1px 3px #0001}
.kpi small{color:#64748b}.kpi div{font-size:20px;font-weight:700}
.fund{border:2px solid #0f766e;border-radius:12px;padding:12px;margin-bottom:14px;background:#f0fdfa}
.fund h3{margin:0 0 4px}.fund button{background:#0f766e;color:#fff;border:0;border-radius:8px;padding:10px 16px;font-size:15px;cursor:pointer}
iframe{width:100%;border:0;min-height:300px}
.side h3{margin:0 0 8px;font-size:15px}.side{display:flex;flex-direction:column;gap:12px}
.log{font:12px/1.45 Consolas,monospace;background:#0f172a;color:#cbd5e1;border-radius:8px;padding:8px;max-height:200px;overflow:auto}
.log .t{color:#5eead4}.log .w{color:#fcd34d}
.tl{list-style:none;margin:0;padding:0;font-size:13px}.tl li{padding:4px 0 4px 18px;position:relative;color:#64748b}
.tl li:before{content:"";position:absolute;left:3px;top:10px;width:8px;height:8px;border-radius:50%;background:#94a3b8}
.tl li.done{color:#0f172a;font-weight:600}.tl li.done:before{background:#0f766e}
.btn{background:#fff;border:1px solid #0f766e;color:#0f766e;border-radius:8px;padding:7px 10px;margin:3px 3px 0 0;cursor:pointer;font-size:13px}
.btn.fill{background:#0f766e;color:#fff}
.muted{color:#64748b;font-size:12px}
@media(max-width:1100px){.wrap{grid-template-columns:1fr}nav{display:none}}
</style></head><body>
<div class="top"><b>BuildRight</b><span>Field service software for contractors (demo app)</span></div>
<div class="banner">Demo with practice data. BuildRight is a pretend partner app; the funding box and the right-hand panel are the real Capital Goose engine in sandbox mode.</div>
<div class="wrap">
<nav><a>Dashboard</a><a>Jobs</a><a>Invoices</a><a>Customers</a><a class="on">Funding</a><a>Reports</a></nav>
<main>
 <div class="kpis"><div class="kpi"><small>Open jobs</small><div>14</div></div><div class="kpi"><small>Unpaid invoices</small><div>$86,400</div></div><div class="kpi"><small>Cash on hand</small><div>$21,300</div></div></div>
 <div class="fund" id="promo"><h3>Need equipment or working capital?</h3>
  <div class="muted" style="margin-bottom:8px">Find out what you qualify for in about two minutes, without leaving BuildRight.</div>
  <button id="open">See what you qualify for</button></div>
 <div class="card" id="widgetCard" style="display:none"><div id="mount"></div>
  <div style="margin-top:8px"><button class="btn fill" id="fill">Demo: fill in sample answers</button>
  <span class="muted">Fills the form for speed. You tick the consent box and sign yourself.</span></div></div>
</main>
<aside class="side">
 <div class="card"><h3>Behind the scenes: API calls</h3><div class="log" id="log"><span class="muted">Nothing yet. Click "See what you qualify for".</span></div></div>
 <div class="card"><h3>File status (tracked by Capital Goose)</h3>
  <div id="ref" class="muted">No file yet.</div><ul class="tl" id="tl"></ul></div>
 <div class="card"><h3>Play the lender</h3><div class="muted">After the file is sent, the lender reports milestones from a private link. Click to simulate that.</div>
  <div id="acts"></div></div>
</aside></div>
<script>
(function(){
var log=document.getElementById('log'),refId=null,frame=null,ORDER=['received','prequalified','submitted','lender_received','approved','closing','funded'];
function L(cls,txt){if(log.querySelector('.muted'))log.innerHTML='';var d=document.createElement('div');d.innerHTML='<span class="'+cls+'">'+new Date().toLocaleTimeString()+'</span> '+txt;log.appendChild(d);log.scrollTop=1e6;}
function load(src){return new Promise(function(ok,no){var s=document.createElement('script');s.src=src;s.onload=ok;s.onerror=no;document.head.appendChild(s);});}
document.getElementById('open').onclick=function(){
  this.disabled=true;
  L('t','BuildRight server -> POST /v1/widget-sessions');
  fetch('/demo/session',{method:'POST'}).then(function(r){return r.json();}).then(function(j){
    L('t','&larr; one-time token (no API key in the browser)');
    return load(j.script_url).then(function(){
      document.getElementById('widgetCard').style.display='block';
      frame=CapitalGooseWidget.mount(document.getElementById('mount'),{token:j.token,onResult:function(r){
        refId=r.referralId;L('t','Widget &rarr; result: <b>'+r.status+'</b> (matched='+r.matched+') id '+r.referralId);poll();}});
      L('t','Embedded widget (iframe from Capital Goose)');
    });
  }).catch(function(){L('w','Could not start the demo. Is DEMO_ENABLED on?');});
};
document.getElementById('fill').onclick=function(){
  try{var f=frame.contentDocument.getElementById('f');if(!f){return;}
  var v={first_name:'Dana',last_name:'Whitfield',email:'dana@buildright-demo.example',dob:'1980-01-01',street:'1 Peachtree St',city:'Atlanta',addr_state:'GA',zip:'30301',credit_band:'720_plus',legal_name:'Whitfield Roofing LLC',state:'GA',years:'6',revenue:'900000',noi:'300000',debt:'100000',amount:'250000'};
  Object.keys(v).forEach(function(k){if(f.elements[k])f.elements[k].value=v[k];});}catch(e){L('w','Could not fill the form: '+e.message);}
};
function poll(){
  if(!refId)return;
  fetch('/demo/referral/'+refId).then(function(r){return r.json();}).then(function(j){
    var reached=ORDER.indexOf(j.status),terminal=ORDER.indexOf(j.status)<0;
    document.getElementById('ref').innerHTML='<b>'+j.status.replace('_',' ')+'</b>'+(j.prequalification.lender?' &middot; '+j.prequalification.lender:'');
    document.getElementById('tl').innerHTML=ORDER.map(function(s,i){return '<li class="'+(i<=reached?'done':'')+'">'+s.replace('_',' ')+'</li>';}).join('')+(terminal?'<li class="done">'+j.status+'</li>':'');
    var acts=(j.actions||[]).map(function(a){return '<button class="btn" data-s="'+a+'">Lender: '+a.replace('_',' ')+'</button>';}).join('');
    if(!acts){acts=j.status==='funded'?'<div style="margin-top:6px"><b>Funded.</b> The demo is complete.</div><button class="btn fill" id="again">Start a new demo</button>':(reached>=ORDER.indexOf('submitted')?'<span class="muted">No further steps.</span>':'<span class="muted">Available once the file is sent to the lender.</span>');}
    document.getElementById('acts').innerHTML=acts;
    var ag=document.getElementById('again');if(ag)ag.onclick=function(){location.reload();};
    Array.prototype.forEach.call(document.querySelectorAll('#acts button'),function(b){b.onclick=function(){
      b.disabled=true;L('w','Lender link &rarr; '+b.dataset.s);
      fetch('/demo/referral/'+refId+'/lender',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:b.dataset.s})}).then(poll);};});
    if(j.status==='submitted'&&!poll.sent){poll.sent=1;L('t','Documents encrypted &rarr; lender emailed a secure link (test inbox in sandbox)');}
    if(j.status==='funded'&&!poll.fundedLogged){poll.fundedLogged=1;L('t','Funded: this counts toward lending accuracy (live partners only; sandbox excluded)');}
  }).catch(function(){});
}
setInterval(poll,3000);
})();
</script></body></html>
"""
