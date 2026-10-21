"""First-party customer dashboard and authenticated workspace discovery."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.api.auth_routes import _authenticated

router = APIRouter(tags=["customer dashboard"])


@router.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def customer_dashboard() -> HTMLResponse:
    """Serve a same-origin, responsive dashboard shell; data always comes from protected APIs."""
    html = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta name="robots" content="noindex,nofollow">
<title>Workspace dashboard | Outreach Marketing Agent</title>
<style>
:root{color-scheme:light;--ink:#152238;--muted:#5b6a80;--line:#dce4ef;--paper:#f4f7fb;--surface:#fff;--blue:#2857c5;--blue-dark:#1c419a;--green:#13795b;--amber:#946200;--red:#b42318}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--blue);text-underline-offset:.2em}button,input,select,textarea{font:inherit}button{cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid #edb949;outline-offset:3px}
.skip{position:absolute;left:-9999px;top:auto}.skip:focus{left:1rem;top:1rem;background:#fff;padding:.7rem;z-index:9}
header{background:#fff;border-bottom:1px solid var(--line)}.topbar{max-width:1240px;margin:auto;padding:1rem 1.25rem;display:flex;align-items:center;justify-content:space-between;gap:1rem}.brand{font-weight:850;color:var(--ink);text-decoration:none;letter-spacing:-.025em}.brand span{color:var(--blue)}
main{max-width:1240px;margin:auto;padding:clamp(1rem,3vw,2rem) 1.25rem 4rem}.muted{color:var(--muted)}.eyebrow{text-transform:uppercase;letter-spacing:.09em;color:var(--blue);font-weight:800;font-size:.76rem}
h1{font-size:clamp(1.8rem,4vw,2.7rem);line-height:1.12;letter-spacing:-.04em;margin:.25rem 0 .6rem}h2{font-size:1.12rem;margin:0 0 .8rem}h3{font-size:1rem;margin:.25rem 0}
button,.button{border:0;border-radius:.65rem;padding:.72rem 1rem;background:var(--blue);color:#fff;font-weight:750;text-decoration:none;display:inline-flex;justify-content:center;align-items:center;gap:.4rem}
button:hover,.button:hover{background:var(--blue-dark)}button.secondary{background:#eaf0fc;color:#1e459f}button.ghost{background:transparent;color:var(--ink);border:1px solid var(--line)}button.danger{background:#fff0ef;color:var(--red)}button:disabled{opacity:.55;cursor:not-allowed}
.panel,.metric,.item{background:var(--surface);border:1px solid var(--line);border-radius:1rem;box-shadow:0 4px 18px #1c355008}.panel{padding:clamp(1rem,2vw,1.5rem)}.grid{display:grid;gap:1rem}.metrics{grid-template-columns:repeat(4,minmax(0,1fr));margin:1.4rem 0}.metric{padding:1.1rem}.metric .num{font-size:1.8rem;font-weight:850;letter-spacing:-.04em}.metric .label{font-size:.85rem;color:var(--muted)}
.columns{grid-template-columns:minmax(0,1.25fr) minmax(280px,.75fr);align-items:start}.stack{display:grid;gap:1rem}.section-head{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap}
label{display:block;font-weight:700;font-size:.88rem;margin:.65rem 0 .3rem}input,select,textarea{width:100%;border:1px solid #cbd5e1;border-radius:.6rem;background:white;color:var(--ink);padding:.72rem .8rem}textarea{min-height:86px;resize:vertical}form .actions{display:flex;gap:.65rem;flex-wrap:wrap;margin-top:1rem}
.auth-wrap{max-width:510px;margin:clamp(1rem,5vw,3rem) auto}.tabs{display:flex;gap:.5rem;margin-bottom:1.25rem}.tabs button{flex:1}.tabs button[aria-pressed=true]{background:var(--blue-dark)}.message{padding:.75rem .9rem;border-radius:.65rem;background:#eef3ff;color:#1e459f;margin:.8rem 0}.message.error{background:#fff0ef;color:var(--red)}.message.success{background:#e8f7f0;color:var(--green)}[hidden]{display:none!important}
.pill{display:inline-flex;padding:.18rem .55rem;border-radius:99px;font-size:.75rem;font-weight:800;background:#edf2fa;color:#3b4d67}.pill.pending{background:#fff3d8;color:var(--amber)}.pill.approved,.pill.success{background:#e4f7ee;color:var(--green)}.pill.rejected,.pill.failed{background:#ffedeb;color:var(--red)}
.list{display:grid;gap:.75rem}.item{padding:1rem}.item-head{display:flex;justify-content:space-between;gap:.75rem;align-items:flex-start}.item p{margin:.4rem 0;color:var(--muted);overflow-wrap:anywhere}.item-actions{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.75rem}.empty{border:1px dashed #c5d0df;border-radius:.8rem;padding:1.2rem;text-align:center;color:var(--muted)}.toolbar{display:flex;align-items:end;gap:.75rem;flex-wrap:wrap}.toolbar>div{flex:1;min-width:210px}.notice{border-left:4px solid #e2aa25;background:#fff8e8;padding:.8rem 1rem;border-radius:.35rem;color:#654a0c}
footer{max-width:1240px;margin:auto;padding:0 1.25rem 2rem;color:var(--muted);font-size:.85rem}
@media(max-width:800px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.columns{grid-template-columns:1fr}.topbar{align-items:flex-start;flex-wrap:wrap}}
@media(max-width:430px){.metrics{gap:.6rem}.metric{padding:.8rem}.metric .num{font-size:1.5rem}.topbar{padding:.85rem 1rem}main{padding-inline:1rem}.item-head{flex-direction:column}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
</style>
</head>
<body>
<a class="skip" href="#main">Skip to main content</a>
<header><div class="topbar"><a class="brand" href="/">Outreach <span>Marketing Agent</span></a><div id="top-actions"><a href="/" class="muted">Public site</a></div></div></header>
<main id="main">
<section id="auth-view" class="auth-wrap panel">
 <p class="eyebrow">Your outreach workspace</p><h1 id="auth-title">Sign in to continue</h1>
 <p class="muted">Research, manage prospects, review campaign drafts, and keep sending decisions under your control.</p>
 <div class="tabs"><button type="button" id="login-tab" aria-pressed="true">Sign in</button><button type="button" id="register-tab" class="secondary" aria-pressed="false">Create account</button></div>
 <form id="auth-form">
  <label for="auth-email">Work email</label><input id="auth-email" name="email" type="email" autocomplete="email" maxlength="320" required>
  <label for="auth-password">Password</label><input id="auth-password" name="password" type="password" autocomplete="current-password" minlength="12" maxlength="1024" required>
  <p id="register-note" class="muted" hidden>Use at least 12 characters. We will email you a verification link before sign-in is enabled.</p>
  <div class="actions"><button id="auth-submit" type="submit">Sign in</button><button id="reset-request" type="button" class="ghost">Forgot password?</button></div>
 </form>
 <div id="auth-message" class="message" role="status" aria-live="polite" hidden></div>
</section>
<section id="dashboard-view" hidden>
 <div class="section-head"><div><p class="eyebrow">Workspace overview</p><h1>Good work starts with evidence.</h1><p class="muted" id="welcome">Your campaigns, prospects, and approvals in one place.</p></div><button id="logout" class="ghost" type="button">Sign out</button></div>
 <div id="global-message" class="message" role="status" aria-live="polite" hidden></div>
 <div class="panel"><div class="toolbar"><div><label for="workspace-select">Active workspace</label><select id="workspace-select"><option value="">Loading workspaces…</option></select></div><div><label for="data-filter">View</label><select id="data-filter"><option value="all">All prospects</option><option value="new">New</option><option value="qualified">Qualified</option><option value="approved">Approved</option><option value="contacted">Contacted</option><option value="replied">Replied</option><option value="converted">Converted</option><option value="do_not_contact">Do not contact</option></select></div><div style="flex:0 0 auto"><button id="refresh" class="secondary" type="button">Refresh data</button></div></div></div>
 <div class="grid metrics" aria-label="Workspace summary">
  <div class="metric"><div class="label">Prospects loaded</div><div id="metric-prospects" class="num">—</div></div>
  <div class="metric"><div class="label">Campaigns</div><div id="metric-campaigns" class="num">—</div></div>
  <div class="metric"><div class="label">Awaiting review</div><div id="metric-pending" class="num">—</div></div>
  <div class="metric"><div class="label">Approved drafts</div><div id="metric-approved" class="num">—</div></div>
 </div>
 <div class="grid columns">
  <div class="stack">
   <section class="panel"><div class="section-head"><h2>Prospect CRM</h2><span class="pill">Workspace-scoped</span></div>
    <details style="margin:.75rem 0 1rem"><summary style="cursor:pointer;font-weight:750;color:var(--blue)">Add a prospect</summary>
     <form id="prospect-form">
      <label for="prospect-name">Contact / creator name</label><input id="prospect-name" maxlength="200" required>
      <label for="prospect-company">Company / publication</label><input id="prospect-company" maxlength="240" required>
      <label for="prospect-role">Role (optional)</label><input id="prospect-role" maxlength="160">
      <label for="prospect-email">Contact email (optional)</label><input id="prospect-email" type="email" maxlength="320">
      <label for="prospect-website">Website URL (HTTPS)</label><input id="prospect-website" type="url" placeholder="https://example.com" maxlength="2048" required>
      <label for="prospect-evidence">Public evidence URL (HTTPS)</label><input id="prospect-evidence" type="url" placeholder="https://example.com/about" maxlength="2048" required>
      <label for="prospect-fit">Why this prospect fits</label><textarea id="prospect-fit" maxlength="2000" required></textarea>
      <div class="actions"><button type="submit">Save prospect</button></div>
     </form>
    </details>
    <div id="prospects-list" class="list"><div class="empty">Choose a workspace to load prospects.</div></div></section>
   <section class="panel"><div class="section-head"><h2>Campaigns</h2><span class="muted">Create and track</span></div>
    <form id="campaign-form">
     <label for="campaign-name">Campaign name</label><input id="campaign-name" maxlength="200" required>
     <label for="business-name">Your business / brand</label><input id="business-name" maxlength="240" required>
     <label for="business-offer">Offer or value proposition</label><textarea id="business-offer" maxlength="2000" required></textarea>
     <label for="target-profile">Target audience</label><textarea id="target-profile" maxlength="2000" required></textarea>
     <div class="actions"><button type="submit">Create campaign</button></div>
    </form><div id="campaigns-list" class="list" style="margin-top:1rem"></div>
   </section>
  </div>
  <div class="stack">
   <section class="panel"><div class="section-head"><h2>Draft approval queue</h2><span class="pill pending">Human review</span></div><p class="muted">Review drafts before any send action. Approval here does not itself send a message.</p><div id="drafts-list" class="list"><div class="empty">Choose a workspace to load drafts.</div></div></section>
   <section class="panel"><div class="section-head"><h2>Delivery activity</h2><span class="pill">Verified status only</span></div><p class="muted">Delivery records reflect provider/queue state, not guaranteed inbox placement.</p><div id="deliveries-list" class="list"><div class="empty">Choose a workspace to load delivery activity.</div></div></section>
   <section class="panel"><h2>Account & safe operation</h2><p id="account-email" class="muted"></p><div class="notice">Live WhatsApp sending is disabled while Meta onboarding and eligibility remain pending. Never treat a draft or approval as proof of delivery.</div><p><a href="/api/v1/billing/entitlements" target="_blank" rel="noreferrer">View current entitlement status</a> · <a href="/docs" target="_blank" rel="noreferrer">API documentation</a></p></section>
  </div>
 </div>
</section>
</main>
<footer>Outreach Marketing Agent · Workspace data is loaded from authenticated APIs. External sending and payment activation remain gated until staging acceptance.</footer>
<script>
(function(){
'use strict';
const $ = (id)=>document.getElementById(id);
const state={mode:'login',csrf:null,user:null,workspaceId:'',workspaces:[],prospects:[],campaigns:[],drafts:[],deliveries:[]};
function message(id,text,type){const el=$(id);el.textContent=text;el.className='message'+(type?' '+type:'');el.hidden=!text;}
function safeText(value){return value==null?'':String(value);}
async function api(path,options){
 const opts=Object.assign({credentials:'same-origin'},options||{});
 opts.headers=Object.assign({'Accept':'application/json'},opts.headers||{});
 if(opts.body && typeof opts.body!=='string'){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(opts.body);}
 if(opts.method && !['GET','HEAD','OPTIONS'].includes(opts.method.toUpperCase()) && state.csrf)opts.headers['X-CSRF-Token']=state.csrf;
 const response=await fetch(path,opts);
 let body=null;try{body=await response.json();}catch(_){}
 if(!response.ok){const err=new Error(body&&body.detail?String(body.detail):'Request failed ('+response.status+')');err.status=response.status;throw err;}
 return body;
}
function node(tag,cls,text){const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=safeText(text);return el;}
function renderEmpty(target,text){$(target).replaceChildren(node('div','empty',text));}
function showAuth(){ $('auth-view').hidden=false;$('dashboard-view').hidden=true;$('top-actions').replaceChildren();const link=node('a','muted','Public site');link.href='/';$('top-actions').append(link);}
function showDashboard(){ $('auth-view').hidden=true;$('dashboard-view').hidden=false;$('account-email').textContent=state.user?state.user.email:'';$('welcome').textContent=state.user?'Signed in as '+state.user.email:'Your campaigns, prospects, and approvals in one place.';$('top-actions').replaceChildren();const link=node('a','muted','Public site');link.href='/';$('top-actions').append(link);}
function setMode(mode){state.mode=mode;const login=mode==='login';$('auth-title').textContent=login?'Sign in to continue':'Create your account';$('auth-submit').textContent=login?'Sign in':'Create account';$('login-tab').setAttribute('aria-pressed',String(login));$('register-tab').setAttribute('aria-pressed',String(!login));$('login-tab').className=login?'':'secondary';$('register-tab').className=login?'secondary':'';$('register-note').hidden=login;$('reset-request').hidden=!login;$('auth-password').autocomplete=login?'current-password':'new-password';$('auth-password').minLength=login?1:12;message('auth-message','');}
$('login-tab').addEventListener('click',()=>setMode('login'));$('register-tab').addEventListener('click',()=>setMode('register'));
$('auth-form').addEventListener('submit',async(e)=>{e.preventDefault();const submit=$('auth-submit');submit.disabled=true;message('auth-message','Working…');try{if(state.mode==='register'){await api('/api/v1/auth/register',{method:'POST',body:{email:$('auth-email').value,password:$('auth-password').value}});message('auth-message','If registration can proceed, a verification email will be sent. Verify your email before signing in.','success');$('auth-form').reset();return;}const result=await api('/api/v1/auth/login',{method:'POST',body:{email:$('auth-email').value,password:$('auth-password').value}});state.csrf=result.csrf_token;state.user=result.user;await loadSession();}catch(err){const friendly=({'authentication_not_configured':'Account service is temporarily unavailable.','email_delivery_not_configured':'Email verification is not configured yet. Contact the site administrator.','verification_delivery_unavailable':'Verification email could not be delivered. Try again later.','email_or_password_incorrect':'Email or password is incorrect, or the email is not verified.','request_origin_rejected':'This request origin was rejected. Open the dashboard from the official site.'})[err.message]||'Could not complete this request. ('+err.message+')';message('auth-message',friendly,'error');}finally{submit.disabled=false;}});
$('reset-request').addEventListener('click',async()=>{const email=$('auth-email').value.trim();if(!email){message('auth-message','Enter your email address first.','error');$('auth-email').focus();return;}try{await api('/api/v1/auth/password-reset/request',{method:'POST',body:{email}});message('auth-message','If the account is eligible, a password-reset email will be sent.','success');}catch(_){message('auth-message','Password reset is temporarily unavailable.','error');}});
async function loadSession(){try{const me=await api('/api/v1/auth/me');state.user=me.user;state.csrf=me.csrf_token||state.csrf;showDashboard();await loadWorkspaces();}catch(_){state.user=null;state.csrf=null;showAuth();}}
async function loadWorkspaces(){const select=$('workspace-select');select.replaceChildren(node('option','','Loading workspaces…'));try{const data=await api('/api/v1/workspaces');state.workspaces=data.items||[];select.replaceChildren();if(!state.workspaces.length){select.append(node('option','','No workspace available'));state.workspaceId='';clearData();message('global-message','No workspace is associated with this account. Contact support to restore workspace access.','error');return;}state.workspaces.forEach(w=>{const option=node('option','',(w.name||'Workspace')+' · '+w.role+' · '+w.id);option.value=w.id;select.append(option);});const prior=state.workspaceId;state.workspaceId=state.workspaces.some(w=>w.id===prior)?prior:state.workspaces[0].id;select.value=state.workspaceId;await loadWorkspaceData();}catch(err){select.replaceChildren(node('option','','Workspace list unavailable'));clearData();message('global-message','Could not load workspaces. '+(err.status===401?'Please sign in again.':'The workspace service may be unavailable.'),'error');}}
function clearData(){state.prospects=[];state.campaigns=[];state.drafts=[];state.deliveries=[];['metric-prospects','metric-campaigns','metric-pending','metric-approved'].forEach(id=>$(id).textContent='—');renderEmpty('prospects-list','No workspace data available.');renderEmpty('campaigns-list','No campaigns loaded.');renderEmpty('drafts-list','No drafts loaded.');renderEmpty('deliveries-list','No delivery activity loaded.');}
async function loadWorkspaceData(){if(!state.workspaceId){clearData();return;}message('global-message','Loading workspace data…');const q='?workspace_id='+encodeURIComponent(state.workspaceId)+'&limit=100';try{const results=await Promise.all([api('/api/v1/prospects'+q),api('/api/v1/campaigns'+q),api('/api/v1/drafts'+q+'&status=all'),api('/api/v1/deliveries'+q)]);state.prospects=results[0].items||[];state.campaigns=results[1].items||[];state.drafts=results[2].items||[];state.deliveries=results[3].items||[];renderData();message('global-message','Workspace data refreshed.','success');}catch(err){clearData();message('global-message',err.status===401?'Your session expired. Please sign in again.':'Workspace data could not be loaded. ('+err.message+')','error');if(err.status===401){state.user=null;showAuth();}}}
function renderData(){const pending=state.drafts.filter(d=>d.status==='pending_approval');$('metric-prospects').textContent=state.prospects.length;$('metric-campaigns').textContent=state.campaigns.length;$('metric-pending').textContent=pending.length;$('metric-approved').textContent=state.drafts.filter(d=>d.status==='approved').length;renderProspects();renderCampaigns();renderDrafts();renderDeliveries();}
function activeRole(){const workspace=state.workspaces.find(w=>w.id===state.workspaceId);return workspace?workspace.role:'viewer';}\nfunction canWrite(){return ['owner','admin','member'].includes(activeRole());}\nfunction renderProspects(){const target=$('prospects-list');target.replaceChildren();const filter=$('data-filter').value;const items=state.prospects.filter(p=>filter==='all'||p.stage===filter);if(!items.length){renderEmpty('prospects-list','No prospects match this view yet.');return;}items.forEach(p=>{const card=node('article','item');const head=node('div','item-head');const left=node('div');left.append(node('h3','',p.name||'Unnamed prospect'));left.append(node('p','',[(p.role||''),(p.company||'')].filter(Boolean).join(' · ')));const pill=node('span','pill',p.stage||'new');head.append(left,pill);card.append(head);if(p.contact_email)card.append(node('p','',p.contact_email));if(p.website_url){const a=node('a','',p.website_url);a.href=p.website_url;a.target='_blank';a.rel='noreferrer';card.append(a);}if(p.fit_reason)card.append(node('p','',p.fit_reason));target.append(card);});}
function renderCampaigns(){const target=$('campaigns-list');target.replaceChildren();if(!state.campaigns.length){renderEmpty('campaigns-list','No campaigns yet. Create one using the form above.');return;}state.campaigns.forEach(c=>{const card=node('article','item');card.append(node('h3','',c.name||'Campaign'));card.append(node('p','',c.client_business||''));card.append(node('p','',c.target_customer_profile||''));target.append(card);});}
function renderDrafts(){const target=$('drafts-list');target.replaceChildren();if(!state.drafts.length){renderEmpty('drafts-list','No drafts found. Draft generation is available only when paid entitlements and valid inputs permit it.');return;}state.drafts.forEach(d=>{const card=node('article','item');const head=node('div','item-head');head.append(node('h3','',d.subject||d.prospect_name||'Outreach draft'));const status=node('span','pill '+(d.status==='approved'?'approved':d.status==='rejected'?'rejected':'pending'),d.status||'unknown');head.append(status);card.append(head);if(d.body)card.append(node('p','',d.body));if(d.channel)card.append(node('p','muted','Channel: '+d.channel));if(d.status==='pending_approval'&&['owner','admin'].includes(activeRole())){const actions=node('div','item-actions');const approve=node('button','','Approve draft');approve.type='button';approve.addEventListener('click',()=>reviewDraft(d.id,'approved'));const reject=node('button','danger','Reject');reject.type='button';reject.addEventListener('click',()=>reviewDraft(d.id,'rejected'));actions.append(approve,reject);card.append(actions);}else if(d.status==='pending_approval'){card.append(node('p','muted','Workspace admin or owner permission is required to review this draft.'));}target.append(card);});}
async function renderDeliveries(){const target=$('deliveries-list');target.replaceChildren();if(!state.deliveries.length){renderEmpty('deliveries-list','No delivery records yet. Approved drafts must be explicitly queued by an authorized workspace admin.');return;}state.deliveries.forEach(d=>{const card=node('article','item');const head=node('div','item-head');head.append(node('h3','',d.subject||d.id||'Delivery'));head.append(node('span','pill '+(d.status==='sent'?'approved':d.status==='failed'?'failed':'pending'),d.status||'unknown'));card.append(head);if(d.channel)card.append(node('p','muted','Channel: '+d.channel));if(d.created_at)card.append(node('p','muted','Queued: '+d.created_at));if(d.error_code)card.append(node('p','', 'Provider status: '+d.error_code));target.append(card);});}
async function reviewDraft(id,decision){if(!confirm('Are you sure you want to '+decision+' this draft? This does not send a message.'))return;try{await api('/api/v1/drafts/'+encodeURIComponent(id)+'/review',{method:'POST',body:{workspace_id:state.workspaceId,decision}});message('global-message','Draft '+decision+'. No message was sent.','success');await loadWorkspaceData();}catch(err){message('global-message','Draft review failed. ('+err.message+')','error');}}
$('prospect-form').addEventListener('submit',async(e)=>{e.preventDefault();if(!state.workspaceId){message('global-message','Choose an active workspace first.','error');return;}if(!canWrite()){message('global-message','Workspace member permission is required to add prospects.','error');return;}const btn=e.submitter;if(btn)btn.disabled=true;try{await api('/api/v1/prospects',{method:'POST',body:{workspace_id:state.workspaceId,name:$('prospect-name').value,company:$('prospect-company').value,role:$('prospect-role').value||null,contact_email:$('prospect-email').value||null,website_url:$('prospect-website').value,evidence_url:$('prospect-evidence').value,fit_reason:$('prospect-fit').value,verified_facts:[]}});$('prospect-form').reset();message('global-message','Prospect saved.','success');await loadWorkspaceData();}catch(err){message('global-message','Prospect could not be saved. Confirm HTTPS URLs and workspace permissions. ('+err.message+')','error');}finally{if(btn)btn.disabled=false;}});
$('campaign-form').addEventListener('submit',async(e)=>{e.preventDefault();if(!state.workspaceId){message('global-message','Choose an active workspace first.','error');return;}if(!canWrite()){message('global-message','Workspace member permission is required to create campaigns.','error');return;}const btn=e.submitter; if(btn)btn.disabled=true;try{await api('/api/v1/campaigns',{method:'POST',body:{workspace_id:state.workspaceId,name:$('campaign-name').value,client_business:$('business-name').value,client_offer:$('business-offer').value,target_customer_profile:$('target-profile').value}});$('campaign-form').reset();message('global-message','Campaign created.','success');await loadWorkspaceData();}catch(err){message('global-message','Campaign creation failed. ('+err.message+')','error');}finally{if(btn)btn.disabled=false;}});
$('workspace-select').addEventListener('change',async()=>{state.workspaceId=$('workspace-select').value;await loadWorkspaceData();});$('data-filter').addEventListener('change',renderProspects);$('refresh').addEventListener('click',loadWorkspaceData);
$('logout').addEventListener('click',async()=>{try{await api('/api/v1/auth/logout',{method:'POST'});}catch(_){}state.user=null;state.csrf=null;state.workspaceId='';showAuth();message('auth-message','You have signed out.','success');});
loadSession();
})();
</script>
</body></html>"""
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        },
    )


@router.get("/api/v1/workspaces")
async def list_current_user_workspaces(request: Request) -> dict:
    """List only workspaces where the authenticated user has active membership."""
    _, _, session = await _authenticated(request)
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="workspace_service_not_configured")
    try:
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                """SELECT w.id::text AS id, 'Workspace'::text AS name, m.role AS role
                   FROM workspaces w
                   JOIN workspace_memberships m ON m.workspace_id=w.id
                   WHERE m.user_id=$1 AND m.status='active'
                   ORDER BY w.created_at ASC, w.id ASC""",
                session["user_id"],
            )
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_list_unavailable") from None
    return {"items": [dict(row) for row in rows]}
