"""
Hosted pre-qualification form + embeddable iframe widget.

Flow: the partner's SERVER calls POST /v1/widget-sessions (API key) and hands the
returned token to the applicant's browser. The browser only ever holds that
single-use, 30-minute token. Consent is captured here, on our own page, with our
own wording and version.
"""
import json
import secrets
from datetime import datetime, timezone
from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine.consent import CONSENT_TEXT, CONSENT_VERSION
from app.engine.lender_links import hash_link_token
from app.engine.ratelimit import SlidingWindowLimiter
from app.engine.referral_service import EngineUnavailable, create_referral, serialize_referral
from app.engine.credit_provider import ProviderNotConfigured
from app.models.partner import Partner, Referral, WidgetSession
from app.schemas.partner_api import ReferralCreate

router = APIRouter()
_limiter = SlidingWindowLimiter(limit=60, window_seconds=60)

_CSS = """
body{font-family:system-ui,sans-serif;margin:0;padding:16px;color:#0f172a;background:#fff}
h2{margin:0 0 4px}h3{margin:20px 0 6px;font-size:15px;color:#334155}
label{display:block;font-size:13px;color:#334155;margin-top:10px}
input,select{width:100%;box-sizing:border-box;font-size:16px;padding:9px;border:1px solid #cbd5e1;border-radius:8px;margin-top:3px}
.row{display:flex;gap:10px}.row>div{flex:1}
.consent{background:#f1f5f9;border-radius:8px;padding:4px 12px;font-size:13px;margin-top:14px}.consent p{margin:8px 0}
.chk{display:flex;gap:8px;align-items:flex-start;margin-top:10px}.chk input{width:auto;margin-top:3px}.chk label{margin:0}
button{margin-top:16px;width:100%;font-size:16px;padding:12px;border:0;border-radius:8px;background:#0f766e;color:#fff;cursor:pointer}
button[disabled]{opacity:.6}.err{color:#b91c1c;font-size:14px;margin-top:10px}.muted{color:#475569;font-size:13px}
.ok{background:#ecfdf5;border:1px solid #6ee7b7;border-radius:10px;padding:14px;margin-top:12px}
.no{background:#f8fafc;border:1px solid #cbd5e1;border-radius:10px;padding:14px;margin-top:12px}
"""


def _client_ip(request: Request):
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


def _load(db, token):
    sess = db.query(WidgetSession).filter(WidgetSession.token_hash == hash_link_token(token)).first()
    if not sess or sess.expires_at < datetime.now(timezone.utc):
        return None, None
    partner = db.query(Partner).filter(Partner.id == sess.partner_id, Partner.active == True).first()  # noqa: E712
    return (sess, partner) if partner else (None, None)


def _html(request, inner, sess=None, status=200, title="Check what you qualify for"):
    nonce = secrets.token_urlsafe(16)
    origin = sess.allowed_origin if sess and sess.allowed_origin else None
    csp = (
        f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
        f"connect-src 'self'; form-action 'none'; base-uri 'none'; "
        f"frame-ancestors {origin or chr(39) + 'none' + chr(39)}"
    )
    body = (
        f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<meta name='robots' content='noindex'><title>{escape(title)}</title><style nonce='{nonce}'>{_CSS}</style></head>"
        f"<body data-origin='{escape(origin or '')}'>{inner.replace('__NONCE__', nonce)}</body></html>"
    )
    return HTMLResponse(body, status_code=status, headers={
        "Content-Security-Policy": csp, "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "X-Robots-Tag": "noindex, nofollow", "X-Content-Type-Options": "nosniff",
    })


def _invalid(request):
    return _html(request, "<h2>Link not available</h2><p class='muted'>This form link is invalid or has expired. "
                          "Please go back and start again.</p>", status=404, title="Link not available")


_JS_FORM = """
(function(){
  var f=document.getElementById('f'), btn=document.getElementById('go'), err=document.getElementById('err');
  var origin=document.body.dataset.origin;
  function post(t,p){ if(origin&&window.parent!==window){ window.parent.postMessage(Object.assign({type:t},p||{}),origin);} }
  function size(){ post('capitalgoose:resize',{height:document.documentElement.scrollHeight}); }
  size(); window.addEventListener('load',size);
  function v(n){return (f.elements[n].value||'').trim();}
  function num(n){var x=parseFloat(v(n).replace(/[$,]/g,''));return isNaN(x)?null:x;}
  f.addEventListener('submit',function(e){
    e.preventDefault(); err.textContent=''; btn.disabled=true;
    var body={
      applicant:{first_name:v('first_name'),last_name:v('last_name'),email:v('email'),phone:v('phone')||null,dob:v('dob'),
        address:{street:v('street'),city:v('city'),state:v('addr_state'),zip:v('zip')}},
      business:{legal_name:v('legal_name'),state:v('state'),industry:'construction',years_in_business:num('years'),
        annual_revenue:num('revenue'),annual_net_operating_income:num('noi'),annual_debt_payments:num('debt')},
      loan:{amount:num('amount'),type:v('loan_type')},
      signer_name:v('signer_name'),consent_accepted:f.elements['consent'].checked
    };
    fetch(location.pathname.replace(/\\/$/,'')+'/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    .then(function(r){return r.json().then(function(j){return {s:r.status,j:j};});})
    .then(function(x){
      if(x.s===200||x.s===409){location.reload();return;}
      var d=x.j.errors?x.j.errors.map(function(e){return e.field+': '+e.message;}).join('\\n'):(x.j.detail||'Something went wrong.');
      err.textContent=d; btn.disabled=false; size();
    }).catch(function(){err.textContent='Network error. Please try again.';btn.disabled=false;});
  });
})();
"""

_JS_RESULT = """
(function(){
  var o=document.body.dataset.origin; if(!o||window.parent===window)return;
  var d=document.getElementById('res').dataset;
  window.parent.postMessage({type:'capitalgoose:result',referral_id:d.ref,status:d.status,matched:d.matched==='true'},o);
  window.parent.postMessage({type:'capitalgoose:resize',height:document.documentElement.scrollHeight},o);
})();
"""


def _field(name, label, value="", type_="text", extra=""):
    return (f"<label>{escape(label)}<input name='{name}' type='{type_}' value='{escape(value)}' {extra} required></label>")


def _form_html(sess, partner):
    pre = json.loads(sess.prefill_json or "{}")
    g = lambda k: pre.get(k, "")   # noqa: E731
    types = [("sba_7a", "SBA 7(a)"), ("sba_504", "SBA 504"), ("equipment", "Equipment"),
             ("working_capital", "Working capital"), ("other", "Other")]
    opts = "".join(f"<option value='{k}'{' selected' if g('loan_type') == k else ''}>{escape(v)}</option>" for k, v in types)
    return f"""
<h2>See what you qualify for</h2>
<p class='muted'>Takes about two minutes. Checking does not affect your credit score.</p>
<form id='f'>
<h3>About you</h3>
<div class='row'><div>{_field('first_name','First name',g('first_name'))}</div><div>{_field('last_name','Last name',g('last_name'))}</div></div>
{_field('email','Email',g('email'),'email')}
<label>Phone (optional)<input name='phone' type='tel'></label>
{_field('dob','Date of birth','', 'date')}
{_field('street','Home street address')}
<div class='row'><div>{_field('city','City')}</div><div>{_field('addr_state','State','', 'text','maxlength=2')}</div><div>{_field('zip','ZIP','', 'text','maxlength=10')}</div></div>
<h3>Your business</h3>
{_field('legal_name','Business legal name',g('legal_name'))}
<div class='row'><div>{_field('state','State of operation',g('state'),'text','maxlength=2')}</div><div>{_field('years','Years in business',g('years_in_business'),'number','min=0 step=0.5')}</div></div>
<div class='row'><div>{_field('revenue','Annual revenue ($)',g('annual_revenue'),'number','min=0')}</div><div>{_field('noi','Annual net operating income ($)','', 'number')}</div></div>
{_field('debt','Annual existing debt payments ($)','', 'number','min=0')}
<h3>What you need</h3>
<div class='row'><div>{_field('amount','Amount requested ($)',g('loan_amount'),'number','min=1')}</div>
<div><label>Type<select name='loan_type'>{opts}</select></label></div></div>
<div class='consent'>{''.join('<p>' + escape(part) + '</p>' for part in CONSENT_TEXT.split(chr(10) * 2))}</div>
<div class='chk'><input type='checkbox' name='consent' id='consent' required><label for='consent'>I have read and agree to the above.</label></div>
{_field('signer_name','Type your full name as your signature')}
<div class='err' id='err' role='alert'></div>
<button id='go' type='submit'>Check what I qualify for</button>
<p class='muted'>Provided on behalf of {escape(partner.name)} by Capital Goose.</p>
</form>
<script nonce='__NONCE__'>{_JS_FORM}</script>
"""


def _result_html(db, referral, partner):
    body = serialize_referral(db, referral)
    pre = body["prequalification"]
    if pre["matched"]:
        reasons = "".join(f"<li>{escape(r)}</li>" for r in pre["reasons"])
        rng = pre.get("likely_range")
        rng_txt = ""
        if rng and (rng.get("min") or rng.get("max")):
            lo = f"${rng['min']:,}" if rng.get("min") else "any amount"
            hi = f"${rng['max']:,}" if rng.get("max") else "no stated maximum"
            rng_txt = f"<p>Typical range this lender funds: {escape(lo)} to {escape(hi)}.</p>"
        inner = (f"<div class='ok'><h2>You may qualify</h2><p>Based on what you told us, <strong>{escape(pre['lender'])}</strong> "
                 f"looks like a good fit.</p>{rng_txt}<ul>{reasons}</ul></div>")
        nxt = f"<p class='muted'>Next, {escape(partner.name)} will follow up to collect your documents. This is not a loan approval or a commitment to lend.</p>"
    else:
        blockers = "".join(f"<li>{escape(b['message'])}</li>" for b in pre["blockers"])
        inner = ("<div class='no'><h2>We couldn't match you right now</h2><p>These are the main reasons:</p>"
                 f"<ul>{blockers}</ul></div>")
        nxt = "<p class='muted'>Your situation may change - you're welcome to check again later.</p>"
    return (f"{inner}{nxt}<div id='res' data-ref='{escape(referral.public_id)}' data-status='{escape(referral.status)}' "
            f"data-matched='{'true' if pre['matched'] else 'false'}'></div><script nonce='__NONCE__'>{_JS_RESULT}</script>")


# Fixed paths first.
@router.get("/embed.js", tags=["widget"])
def embed_js():
    js = """(function(w){
  var script=document.currentScript, base=script?new URL(script.src).origin:'';
  w.CapitalGooseWidget={mount:function(el,opts){
    if(!el||!opts||!opts.token)throw new Error('CapitalGooseWidget.mount(el,{token})');
    var f=document.createElement('iframe');
    f.src=base+'/widget/'+encodeURIComponent(opts.token);
    f.title='Check what you qualify for'; f.referrerPolicy='no-referrer';
    f.style.cssText='width:100%;border:0;min-height:720px';
    el.appendChild(f);
    w.addEventListener('message',function(e){
      if(e.origin!==base||e.source!==f.contentWindow||!e.data||typeof e.data.type!=='string')return;
      if(e.data.type==='capitalgoose:resize'&&e.data.height)f.style.height=Math.min(e.data.height,4000)+'px';
      if(e.data.type==='capitalgoose:result'&&opts.onResult)opts.onResult({referralId:e.data.referral_id,status:e.data.status,matched:e.data.matched});
    });
    return f;
  }};
})(window);
"""
    return Response(js, media_type="application/javascript", headers={"Cache-Control": "public, max-age=300"})


@router.get("/{token}", response_class=HTMLResponse, tags=["widget"])
def show(token: str, request: Request, db: Session = Depends(get_db)):
    if not _limiter.allow(_client_ip(request)):
        return _html(request, "<p>Too many requests. Please wait a minute.</p>", status=429)
    sess, partner = _load(db, token)
    if not sess:
        return _invalid(request)
    if sess.referral_id:
        referral = db.query(Referral).filter(Referral.id == sess.referral_id).first()
        return _html(request, _result_html(db, referral, partner), sess)
    return _html(request, _form_html(sess, partner), sess)


@router.post("/{token}/submit", tags=["widget"])
async def submit(token: str, request: Request, db: Session = Depends(get_db)):
    if not _limiter.allow(_client_ip(request)):
        return JSONResponse({"detail": "Too many requests. Please wait a minute."}, status_code=429)
    sess, partner = _load(db, token)
    if not sess:
        return JSONResponse({"detail": "This form link has expired."}, status_code=404)
    if sess.referral_id:
        return JSONResponse({"detail": "Already submitted"}, status_code=409)
    try:
        body = json.loads((await request.body()) or b"{}")
        if not isinstance(body, dict):
            raise ValueError
    except ValueError:
        return JSONResponse({"detail": "Invalid request"}, status_code=422)

    data = {
        "external_ref": sess.external_ref,
        "applicant": body.get("applicant"),
        "business": body.get("business"),
        "loan": body.get("loan"),
        "consent": {
            "accepted": body.get("consent_accepted") is True,
            "signer_name": str(body.get("signer_name") or ""),
            "consent_version": CONSENT_VERSION,            # OUR wording and version, not the browser's
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "ip_address": _client_ip(request),
        },
    }
    try:
        payload = ReferralCreate.model_validate(data)
    except ValidationError as e:
        return JSONResponse({"errors": [
            {"field": ".".join(str(x) for x in err["loc"]), "message": err["msg"]} for err in e.errors()
        ]}, status_code=422)

    try:
        referral, _ = create_referral(db, partner, payload, idempotency_key=f"widget:{sess.id}", partner_ip=_client_ip(request))
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    except (EngineUnavailable, ProviderNotConfigured):
        return JSONResponse({"detail": "This service is temporarily unavailable."}, status_code=503)
    except Exception:
        db.rollback()
        return JSONResponse({"detail": "We couldn't complete the check. Please try again."}, status_code=502)

    sess.referral_id = referral.id
    db.commit()
    return {"ok": True}
