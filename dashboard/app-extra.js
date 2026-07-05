/* =====================================================
   RESO DASHBOARD — All Tab Functions + Init
   ===================================================== */

const API='https://salmanch123-reso.hf.space';
let isOffline=false;
let paillierQueue=[];
let disclosureActive=null;
let disclosureTimer=null;
let escrowPoller=null;
let _proofs=0,_verified=0,_blocked=0;

function bumpCounter(ok){
  _proofs++;if(ok)_verified++;else _blocked++;
  const pEl=document.getElementById('pcProofs');
  const vEl=document.getElementById('pcVerified');
  const bEl=document.getElementById('pcBlocked');
  if(pEl)pEl.textContent=_proofs;
  if(vEl)vEl.textContent=_verified;
  if(bEl)bEl.textContent=_blocked;
  [pEl,vEl,bEl].filter(Boolean).forEach(el=>{
    el.classList.add('flash');setTimeout(()=>el.classList.remove('flash'),400);
  });
}

function showToast(msg,ok=true){
  const t=document.getElementById('toast');
  if(!t)return;
  document.getElementById('toastText').innerText=msg;
  const ico=document.getElementById('toastIcon');
  ico.className=ok?'toast-ok':'toast-err';
  ico.innerHTML=ok
    ?'<i class="hgi-stroke hgi-checkmark-circle-01"></i>'
    :'<i class="hgi-stroke hgi-cancel-01"></i>';
  t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2800);
}

function setOffline(){
  isOffline=true;
  const bar=document.getElementById('offlineBar');
  if(bar)bar.style.display='block';
  const lbl=document.getElementById('statusLabel');
  if(lbl)lbl.textContent='Demo Mode';
  const dot=document.querySelector('.status-dot');
  const badge=document.querySelector('.status-badge');
  if(dot){dot.style.background='var(--amber)';dot.style.boxShadow='0 0 8px rgba(245,158,11,.4)';}
  if(badge){badge.style.borderColor='rgba(245,158,11,.3)';badge.style.background='rgba(245,158,11,.08)';badge.style.color='var(--amber)';}
}

function showResult(id,html,type='info'){
  const el=document.getElementById(id);
  if(!el)return;
  el.innerHTML=html;el.className='result-box '+type;el.style.display='block';
}

function switchTab(id,el){
  document.querySelectorAll('.nav-tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  clearInterval(escrowPoller);
  if(el)el.classList.add('active');
  const panel=document.getElementById('panel-'+id);
  if(panel)panel.classList.add('active');
  if(id==='escrow'){loadEscrows();escrowPoller=setInterval(loadEscrows,3000);}
  if(id==='sandbox'){loadRevocation();loadFolding();}
}

// ---- WALLETS ----
function renderWallets(data){
  const mr=document.getElementById('merkleRoot');
  if(mr)mr.textContent='0x'+data.sanctions_merkle_root.slice(0,16)+'...';
  const wl=document.getElementById('walletList');if(wl)wl.innerHTML='';
  const sels=['simSender','revokeSelect','escrowSender','escrowRecipient'];
  const saved=sels.map(id=>document.getElementById(id)&&document.getElementById(id).value);
  sels.forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML='';});
  data.wallets.forEach(w=>{
    if(wl){
      const item=document.createElement('div');item.className='list-item';
      item.innerHTML=`<div class="item-meta"><span class="item-name">${w.name||'Anon'}</span><span class="item-sub">${w.address.slice(0,10)}...${w.address.slice(-8)}</span></div><div style="display:flex;gap:4px;flex-shrink:0">${w.is_sanctioned?'<span class="badge b-sanctioned">Sanctioned</span>':''}<span class="badge b-tier">Tier ${w.kyc_tier}</span></div>`;
      wl.appendChild(item);
    }
    sels.forEach(id=>{
      const sel=document.getElementById(id);if(!sel)return;
      const o=document.createElement('option');o.value=w.address;
      o.textContent=`${w.name||w.address.slice(0,8)} (${w.address.slice(0,8)}...)`;
      sel.appendChild(o);
    });
  });
  sels.forEach((id,i)=>{
    const el=document.getElementById(id);
    if(el&&saved[i]&&[...el.options].some(o=>o.value===saved[i]))el.value=saved[i];
  });
}

function loadDemoMode(){
  setOffline();
  const demos=[
    {address:'GCLEANUSERADDRESSTHATISFINE00099',name:'Alice (Tier 2)',kyc_tier:2,is_sanctioned:false},
    {address:'GBASICKYCUSERADDRESS00000000001',name:'Bob (Tier 1)',kyc_tier:1,is_sanctioned:false},
    {address:'GNOKYCUSERADDRESS000000000000002',name:'Charlie (No KYC)',kyc_tier:0,is_sanctioned:false},
    {address:'GABC1SANCTIONEDEXAMPLEADDRESS0001',name:'Sanctioned Entity',kyc_tier:1,is_sanctioned:true},
  ];
  renderWallets({wallets:demos,sanctions_merkle_root:'DEMO_OFFLINE_ROOT'});
  const aRows=document.getElementById('auditRows');
  if(aRows)aRows.innerHTML=`<tr><td>${new Date().toLocaleString()}</td><td>Sanctions screen</td><td><span class="badge b-blocked">Blocked</span></td><td class="mono">0xdemo1...</td><td class="mono">0xdemo...</td></tr><tr><td>${new Date().toLocaleString()}</td><td>All checks passed</td><td><span class="badge b-ok">Verified</span></td><td class="mono">0xdemo2...</td><td class="mono">0xdemo...</td></tr>`;
  const revRoot=document.getElementById('revRoot');if(revRoot)revRoot.textContent='0xDEMO...OFFLINE';
  const fRoot=document.getElementById('foldingRoot');if(fRoot)fRoot.textContent='0xDEMO...OFFLINE';
}

async function loadRules(){
  try{
    const r=await fetch(`${API}/api/rules`);if(!r.ok)throw new Error();
    const d=await r.json();
    const ma=document.getElementById('maxAmount');if(ma)ma.value=d.max_amount;
    const dl=document.getElementById('dailyLimit');if(dl)dl.value=d.daily_limit;
    const kt=document.getElementById('kycTier');if(kt)kt.value=d.min_kyc_tier;
    const sc=document.getElementById('sanctionsCheck');if(sc)sc.value=d.sanctions_enabled.toString();
  }catch(e){loadDemoMode();}
}
async function saveRules(){
  if(isOffline){showToast('Demo mode — backend offline.',false);return;}
  const body={max_amount:+document.getElementById('maxAmount').value,daily_limit:+document.getElementById('dailyLimit').value,min_kyc_tier:+document.getElementById('kycTier').value,sanctions_enabled:document.getElementById('sanctionsCheck').value==='true'};
  try{const r=await fetch(`${API}/api/rules`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(r.ok)showToast('Rules published!');}catch(e){showToast('Error.',false);}
}
async function loadWallets(){
  if(isOffline)return;
  try{const r=await fetch(`${API}/api/wallets`);if(!r.ok)throw new Error();renderWallets(await r.json());}catch(e){}
}
async function submitWallet(){
  if(isOffline){showToast('Demo mode.',false);closeWalletModal();return;}
  const addr=document.getElementById('nwAddr').value.trim();if(!addr){alert('Address required');return;}
  try{const r=await fetch(`${API}/api/wallets`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({address:addr,name:document.getElementById('nwName').value.trim()||'User',kyc_tier:+document.getElementById('nwKyc').value,is_sanctioned:document.getElementById('nwSanc').value==='true'})});if(r.ok){showToast('Wallet registered!');closeWalletModal();loadWallets();}}
  catch(e){showToast('Error.',false);}
}
function openWalletModal(){const m=document.getElementById('walletModal');if(m)m.style.display='flex';}
function closeWalletModal(){const m=document.getElementById('walletModal');if(m)m.style.display='none';}
async function loadAuditLogs(){
  if(isOffline)return;
  try{const r=await fetch(`${API}/api/audit-logs`);if(!r.ok)throw new Error();
  const logs=await r.json();const tbody=document.getElementById('auditRows');if(!tbody)return;tbody.innerHTML='';
  logs.forEach(l=>{const tr=document.createElement('tr');const badge=l.status==='ok'?'<span class="badge b-ok">Verified</span>':'<span class="badge b-blocked">Blocked</span>';tr.innerHTML=`<td>${l.timestamp}</td><td>${l.rule_checked}</td><td>${badge}</td><td class="mono">${l.merkle_root}</td><td class="mono" title="${l.proof_ref}">${l.proof_ref.slice(0,12)}...</td>`;tbody.appendChild(tr);});
  }catch(e){}
}

// ---- CIRCUIT ----
const STEPS=['rev','san','kyc','lim','proof'];

function rndHash(){return'0x'+Array.from({length:12},()=>Math.floor(Math.random()*16).toString(16)).join('');}
function delay(ms){return new Promise(r=>setTimeout(r,ms));}

function resetCircuit(){
  STEPS.forEach(id=>{
    const cn=document.getElementById('cn-'+id);if(cn)cn.className='cn';
    const ps=document.getElementById('ps-'+id);if(ps)ps.className='pstep';
    const ph=document.getElementById('ph-'+id);if(ph)ph.style.opacity='0';
  });
  const scan=document.getElementById('circuitScan');if(scan)scan.style.left='-4px';
  const wrap=document.getElementById('circuitWrap');if(wrap)wrap.classList.remove('running');
  const badge=document.getElementById('phBadge');if(badge)badge.className='ph-badge';
  const badgeTxt=document.getElementById('phBadgeTxt');if(badgeTxt)badgeTxt.textContent='Ready';
}

async function animateCircuit(results){
  const wrap=document.getElementById('circuitWrap');
  const scan=document.getElementById('circuitScan');
  const badge=document.getElementById('phBadge');
  if(!wrap||!scan||!badge)return true;
  wrap.classList.add('running');
  badge.className='ph-badge running';
  const badgeTxt=document.getElementById('phBadgeTxt');if(badgeTxt)badgeTxt.textContent='Generating Proof...';
  for(let i=0;i<STEPS.length;i++){
    const pct=(i/(STEPS.length-1))*100;
    scan.style.animation='none';scan.style.left=pct+'%';void scan.offsetWidth;
    const cn=document.getElementById('cn-'+STEPS[i]);if(cn)cn.className='cn active';
    const ps=document.getElementById('ps-'+STEPS[i]);if(ps)ps.className='pstep active';
    await delay(results[i].ok!==false?380:250);
    const ok=results[i].ok!==false;
    if(cn)cn.className=ok?'cn done':'cn fail';
    if(ps)ps.className=ok?'pstep done':'pstep fail';
    const ph=document.getElementById('ph-'+STEPS[i]);if(ph)ph.textContent=(STEPS[i]==='proof'?'bn254':'sha256')+'::'+rndHash();
    if(!ok){
      wrap.classList.remove('running');
      badge.className='ph-badge';
      if(badgeTxt)badgeTxt.textContent='Proof Failed';
      return false;
    }
  }
  wrap.classList.remove('running');badge.className='ph-badge done';
  if(badgeTxt)badgeTxt.textContent='Proof Verified';
  return true;
}

function showProofResult(ok,title,body,hash){
  const el=document.getElementById('simResult');if(!el)return;
  el.style.display='block';el.className='proof-result '+(ok?'ok':'fail');
  const pt=document.getElementById('prTitle');if(pt)pt.innerHTML=(ok?'<i class="hgi-stroke hgi-checkmark-circle-01"></i> ':'<i class="hgi-stroke hgi-cancel-01"></i> ')+title;
  const pb=document.getElementById('prBody');if(pb)pb.innerHTML=body;
  const hashEl=document.getElementById('prHash');if(!hashEl)return;
  hashEl.textContent='';hashEl.classList.add('cursor');
  const fullHash='groth16::'+hash;let i=0;
  const ti=setInterval(()=>{hashEl.textContent+=fullHash[i]||'';i++;if(i>=fullHash.length){clearInterval(ti);hashEl.classList.remove('cursor');}},30);
}

async function runSimulation(){
  const senderEl=document.getElementById('simSender');
  const amountEl=document.getElementById('simAmount');
  const sender=senderEl?senderEl.value:'';
  const amount=amountEl?+amountEl.value:0;
  if(!sender){showToast('Register a wallet first.',false);return;}
  resetCircuit();
  const sr=document.getElementById('simResult');if(sr)sr.style.display='none';
  if(isOffline){
    const fakeResults=STEPS.map(()=>({ok:true}));
    await animateCircuit(fakeResults);
    bumpCounter(true);
    showProofResult(true,'Demo Mode: All ZK Checks Passed','Connect backend for real on-chain verification.',rndHash());
    return;
  }
  try{
    const r=await fetch(`${API}/api/simulate-transfer`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sender,amount})});
    const d=await r.json();const ok=d.compliant;
    const stepResults=STEPS.map((s)=>{
      if(ok)return{ok:true};
      const reason=d.reason||'';
      if(s==='rev'&&(d.event&&d.event.rule_checked||'').includes('revocation'))return{ok:false};
      if(s==='san'&&reason.includes('sanctions'))return{ok:false};
      if(s==='kyc'&&reason.includes('KYC'))return{ok:false};
      if(s==='lim'&&reason.includes('exceed'))return{ok:false};
      return{ok:true};
    });
    await animateCircuit(stepResults);
    bumpCounter(ok);
    if(ok){showProofResult(true,'Transaction Verified',`Rule: ${d.event&&d.event.rule_checked||'All checks passed'}`,d.event&&d.event.proof_ref||rndHash());}
    else{showProofResult(false,'Transaction Blocked',`Rule: ${d.event&&d.event.rule_checked||''}<br>${d.reason}`,d.event&&d.event.proof_ref||rndHash());}
    loadWallets();loadAuditLogs();
  }catch(e){showToast('Simulation error.',false);resetCircuit();}
}

// ---- ESCROW ----
async function loadEscrows(){
  if(isOffline){const el=document.getElementById('escrowsList');if(el)el.innerHTML="<div style='padding:12px;font-size:12px;color:var(--text3)'>Backend offline.</div>";return;}
  try{const r=await fetch(`${API}/api/escrow`);if(!r.ok)throw new Error();
  const data=await r.json();const out=document.getElementById('escrowsList');if(!out)return;out.innerHTML='';
  if(!data.escrows.length){out.innerHTML="<div style='padding:12px;font-size:12px;color:var(--text3)'>No active escrows.</div>";return;}
  const now=Math.floor(Date.now()/1000);
  data.escrows.forEach(e=>{
    const item=document.createElement('div');item.className='list-item';
    const td=e.unlock_time-now;const locked=td>0;
    item.innerHTML=`<div class="item-meta"><span class="item-name">${e.amount} USD → ${e.recipient.slice(0,8)}...</span><span class="item-sub">From ${e.sender.slice(0,8)}...</span></div><div style="display:flex;gap:4px;align-items:center;flex-shrink:0">${locked?`<span class="badge b-tier">Locked ${td}s</span>`:'<span class="badge b-ok">Claimable</span>'}<button class="btn purple" style="font-size:10px;padding:3px 8px;flex:none" onclick="claimEscrow('${e.recipient}')">Claim</button><button class="btn red" style="font-size:10px;padding:3px 8px;flex:none" onclick="refundEscrow('${e.recipient}')" ${locked?'disabled':''}>Refund</button></div>`;
    out.appendChild(item);
  });}catch(e){}
}
async function depositEscrow(){
  if(isOffline){showToast('Demo mode.',false);return;}
  const sender=document.getElementById('escrowSender').value;const recipient=document.getElementById('escrowRecipient').value;
  if(sender===recipient){alert('Sender == recipient');return;}
  try{const r=await fetch(`${API}/api/escrow/deposit`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sender,recipient,amount:+document.getElementById('escrowAmount').value,unlock_delay_sec:+document.getElementById('escrowDelay').value})});if(r.ok){showToast('Escrow deposited!');loadEscrows();}else{const e=await r.json();alert(e.detail);}}
  catch(e){showToast('Error.',false);}
}
async function claimEscrow(recipient){
  if(isOffline){showToast('Demo mode.',false);return;}
  const proof=prompt('ZK Proof:','11223344');if(!proof)return;
  try{const r=await fetch(`${API}/api/escrow/claim`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({recipient,proof})});if(r.ok){showToast('Escrow claimed!');loadEscrows();}else{const e=await r.json();alert(e.detail);}}
  catch(e){showToast('Error.',false);}
}
async function refundEscrow(recipient){
  if(isOffline){showToast('Demo mode.',false);return;}
  try{const r=await fetch(`${API}/api/escrow/refund`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({recipient})});if(r.ok){showToast('Escrow refunded!');loadEscrows();}else{const e=await r.json();alert(e.detail);}}
  catch(e){showToast('Error.',false);}
}

// ---- STELLAR ----
async function apiPost(path,body,resultId){const el=document.getElementById(resultId);if(el)el.style.display='none';try{const r=await fetch(`${API}${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw new Error(d.detail||JSON.stringify(d));return d;}catch(e){showResult(resultId,`<strong>Error:</strong> ${e.message}`,'fail');return null;}}
async function apiGet(path,resultId){const el=document.getElementById(resultId);if(el)el.style.display='none';try{const r=await fetch(`${API}${path}`);const d=await r.json();if(!r.ok)throw new Error(d.detail||JSON.stringify(d));return d;}catch(e){showResult(resultId,`<strong>Error:</strong> ${e.message}`,'fail');return null;}}

async function stellarCreateAccount(){const label=document.getElementById('newAccLabel').value.trim();showResult('createAccResult','Calling Friendbot… (~5s)','info');const d=await apiPost('/api/stellar/create-account',{label},'createAccResult');if(!d)return;showResult('createAccResult',`<strong>Account Created</strong><br><b>Public:</b> <span class="mono">${d.public_key}</span><br><b>Secret:</b> <span class="mono" style="color:var(--red)">${d.secret_key}</span><br><b>Balance:</b> ${d.starting_balance}<br><a class="tx-link" href="${d.explorer}" target="_blank">View on Stellar.Expert →</a>`,'ok');showToast('Account created!');}
async function stellarInspect(){const addr=document.getElementById('inspectAddr').value.trim();if(!addr){showToast('Enter a public key.',false);return;}showResult('inspectResult','Loading…','info');const d=await apiGet(`/api/stellar/account/${addr}`,'inspectResult');if(!d)return;const bals=d.balances.map(b=>`<span class="badge b-gold">${b.balance} ${b.asset_type==='native'?'XLM':b.asset_code}</span>`).join(' ');showResult('inspectResult',`<b>Sequence:</b> ${d.sequence}<br><b>Balances:</b> ${bals}<br><a class="tx-link" href="${d.explorer}" target="_blank">View →</a>`,'info');}
async function stellarTransfer(){const secret=document.getElementById('transferSecret').value.trim();const dest=document.getElementById('transferDest').value.trim();const amount=document.getElementById('transferAmt').value;const memo=document.getElementById('transferMemo').value.trim();if(!secret||!dest){showToast('Secret key and destination required.',false);return;}showResult('transferResult','Submitting…','info');const d=await apiPost('/api/stellar/transfer',{source_secret:secret,destination:dest,amount,memo:memo||'Reso'},'transferResult');if(!d)return;showResult('transferResult',`<strong>Transfer Confirmed</strong><br><a class="tx-link" href="${d.explorer}" target="_blank">View Transaction →</a>`,'ok');showToast('XLM sent!');loadAuditLogs();}
async function stellarLoadTxHistory(){const addr=document.getElementById('txHistAddr').value.trim();if(!addr){showToast('Enter public key.',false);return;}const d=await apiGet(`/api/stellar/transactions/${addr}`,'inspectResult');if(!d)return;const tbody=document.getElementById('txHistRows');if(!tbody)return;tbody.innerHTML='';if(!d.payments.length){tbody.innerHTML='<tr><td colspan="5" style="color:var(--text3)">No payments found.</td></tr>';return;}d.payments.forEach(p=>{const tr=document.createElement('tr');const dir=p.to===addr?'<span class="badge b-ok">↓ In</span>':'<span class="badge b-blocked">↑ Out</span>';tr.innerHTML=`<td>${p.created_at.slice(0,10)}</td><td>${dir}</td><td>${p.amount||'-'}</td><td>${p.asset_code||'XLM'}</td><td><a class="tx-link" href="${p.explorer}" target="_blank">${p.hash.slice(0,10)}…</a></td>`;tbody.appendChild(tr);});}
async function stellarMultisig(){const secret=document.getElementById('msigSecret').value.trim();const newSigner=document.getElementById('msigNewSigner').value.trim();const weight=+document.getElementById('msigWeight').value;const med=+document.getElementById('msigThreshold').value;if(!secret||!newSigner){showToast('All fields required.',false);return;}showResult('msigResult','Configuring…','info');const d=await apiPost('/api/stellar/multisig/setup',{account_secret:secret,new_signer_public:newSigner,weight,med_threshold:med,low_threshold:1,high_threshold:med},'msigResult');if(!d)return;showResult('msigResult',`<strong>Multisig Configured</strong><br><a class="tx-link" href="${d.explorer}" target="_blank">View →</a>`,'ok');showToast('Multisig configured!');}
async function stellarPathPayment(){const secret=document.getElementById('pathSecret').value.trim();const dest=document.getElementById('pathDest').value.trim();const destCode=document.getElementById('pathDestCode').value.trim();const destAmt=document.getElementById('pathDestAmt').value;if(!secret||!dest){showToast('Secret and destination required.',false);return;}showResult('pathResult','Finding path…','info');const d=await apiPost('/api/stellar/path-payment',{source_secret:secret,destination:dest,dest_asset_code:destCode||'XLM',dest_asset_issuer:document.getElementById('pathDestIssuer').value.trim(),dest_amount:destAmt,send_asset_code:'XLM'},'pathResult');if(!d)return;showResult('pathResult',`<strong>Path Payment Sent</strong><br><a class="tx-link" href="${d.explorer}" target="_blank">View →</a>`,'ok');showToast('Path payment executed!');}
async function stellarIssueAsset(){const issuerSecret=document.getElementById('issuerSecret').value.trim();const distSecret=document.getElementById('distSecret').value.trim();const code=document.getElementById('assetCode').value.trim().toUpperCase();const amount=document.getElementById('assetSupply').value;if(!issuerSecret||!distSecret||!code){showToast('All fields required.',false);return;}showResult('issueResult','Issuing asset (~10s)…','info');const d=await apiPost('/api/stellar/issue-asset',{issuer_secret:issuerSecret,distributor_secret:distSecret,asset_code:code,amount},'issueResult');if(!d)return;showResult('issueResult',`<strong>Asset Issued</strong><br><b>Code:</b> ${d.asset_code}<br><a class="tx-link" href="${d.explorer_asset}" target="_blank">View →</a>`,'ok');showToast('Asset issued!');}
async function stellarTrustline(){const secret=document.getElementById('trustSecret').value.trim();const code=document.getElementById('trustAssetCode').value.trim().toUpperCase();const issuer=document.getElementById('trustIssuer').value.trim();if(!secret||!code||!issuer){showToast('All fields required.',false);return;}showResult('trustResult','Adding trustline…','info');const d=await apiPost('/api/stellar/trustline',{account_secret:secret,asset_code:code,issuer},'trustResult');if(!d)return;showResult('trustResult',`<strong>Trustline Added</strong><br><a class="tx-link" href="${d.explorer}" target="_blank">View →</a>`,'ok');showToast('Trustline added!');}
async function stellarCreateClaimable(){const secret=document.getElementById('claimSrcSecret').value.trim();const claimant=document.getElementById('claimClaimant').value.trim();const amount=document.getElementById('claimAmt').value;const d2=+document.getElementById('claimDelay').value;if(!secret||!claimant){showToast('All fields required.',false);return;}showResult('claimCreateResult','Creating…','info');const d=await apiPost('/api/stellar/claimable-balance/create',{source_secret:secret,claimant,amount,unlock_delay_sec:d2},'claimCreateResult');if(!d)return;showResult('claimCreateResult',`<strong>Claimable Balance Created</strong><br><b>Balance ID:</b> <span class="mono">${d.balance_id||'See explorer'}</span><br><a class="tx-link" href="${d.explorer}" target="_blank">View →</a>`,'ok');showToast('Funds locked!');}
async function stellarClaimBalance(){const secret=document.getElementById('claimSecret').value.trim();const balanceId=document.getElementById('claimBalanceId').value.trim();if(!secret||!balanceId){showToast('All fields required.',false);return;}showResult('claimResult','Claiming…','info');const d=await apiPost('/api/stellar/claimable-balance/claim',{claimant_secret:secret,balance_id:balanceId},'claimResult');if(!d)return;showResult('claimResult',`<strong>Balance Claimed</strong><br><a class="tx-link" href="${d.explorer}" target="_blank">View →</a>`,'ok');showToast('Claimed!');}
async function stellarOrderbook(){const sell=document.getElementById('obSell').value;const buyCode=document.getElementById('obBuyCode').value.trim().toUpperCase();const buyIssuer=document.getElementById('obBuyIssuer').value.trim();const d=await apiGet(`/api/stellar/orderbook?selling=${sell}&buying=${buyCode}&buying_issuer=${buyIssuer}`,'inspectResult');if(!d)return;const tbody=document.getElementById('obRows');if(!tbody)return;tbody.innerHTML='';if(!d.bids.length&&!d.asks.length){tbody.innerHTML='<tr><td colspan="3" style="color:var(--text3)">No orders found.</td></tr>';return;}d.bids.forEach(b=>{const tr=document.createElement('tr');tr.innerHTML=`<td><span class="badge b-ok">Bid</span></td><td>${b.price}</td><td>${b.amount}</td>`;tbody.appendChild(tr);});d.asks.forEach(a=>{const tr=document.createElement('tr');tr.innerHTML=`<td><span class="badge b-blocked">Ask</span></td><td>${a.price}</td><td>${a.amount}</td>`;tbody.appendChild(tr);});}
async function stellarOffer(){const secret=document.getElementById('offerSecret').value.trim();const buyCode=document.getElementById('offerBuyCode').value.trim().toUpperCase();const buyIssuer=document.getElementById('offerBuyIssuer').value.trim();const amt=document.getElementById('offerAmt').value;const price=document.getElementById('offerPrice').value;if(!secret||!buyCode||!buyIssuer){showToast('All fields required.',false);return;}showResult('offerResult','Posting offer…','info');const d=await apiPost('/api/stellar/manage-offer',{account_secret:secret,selling_code:'XLM',selling_issuer:'',buying_code:buyCode,buying_issuer:buyIssuer,amount:amt,price},'offerResult');if(!d)return;showResult('offerResult',`<strong>Offer Posted</strong><br><a class="tx-link" href="${d.explorer}" target="_blank">View →</a>`,'ok');showToast('DEX offer placed!');}

// ---- SANDBOX ----
function loadPaillierQueue(){const el=document.getElementById('paillierQueue');if(el)el.innerHTML=paillierQueue.length?paillierQueue.map((c,i)=>`[Tx #${i+1}] ${c.slice(0,28)}...`).join('<br>'):'Empty.';}
async function paillierEncrypt(){if(isOffline){showToast('Demo mode.',false);return;}const m=+document.getElementById('paillierAmt').value;try{const r=await fetch(`${API}/api/crypto/paillier/encrypt`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:m})});const d=await r.json();paillierQueue.push(d.ciphertext);loadPaillierQueue();showToast(`Encrypted ${m} USD.`);}catch(e){showToast('Error.',false);}}
async function paillierSum(){if(isOffline){showToast('Demo mode.',false);return;}if(!paillierQueue.length){alert('Queue empty!');return;}try{const r=await fetch(`${API}/api/crypto/paillier/sum-and-check`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ciphertexts:paillierQueue,limit:25000})});const d=await r.json();const el=document.getElementById('paillierResult');if(el)el.innerHTML=`Sum: ${d.decrypted_sum} USD — Within limit? <strong style="color:${d.within_limit?'var(--green)':'var(--red)'}">${d.within_limit?'Yes':'No'}</strong>`;}catch(e){showToast('Error.',false);}}
async function paillierReset(){paillierQueue=[];loadPaillierQueue();const el=document.getElementById('paillierResult');if(el)el.innerHTML='';if(isOffline)return;try{await fetch(`${API}/api/crypto/paillier/keygen`,{method:'POST'});showToast('New keypair generated.');}catch(e){}}
async function disclosureOpen(){if(isOffline){showToast('Demo mode.',false);return;}const identity=+document.getElementById('identityCommit').value;for(let i=1;i<=5;i++){const btn=document.getElementById('tb-'+i);if(btn)btn.className='trustee-btn';}try{const r=await fetch(`${API}/api/crypto/disclosure/open`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({identity_commitment:identity,threshold:3,n:5,delay_sec:10})});disclosureActive=await r.json();let t=10;clearInterval(disclosureTimer);const ds=document.getElementById('disclosureStatus');if(ds)ds.textContent=`Time lock: ${t}s remaining.`;disclosureTimer=setInterval(()=>{t--;if(t<=0){clearInterval(disclosureTimer);if(ds)ds.textContent='Lock expired. Collect 3 approvals then decrypt.';}else if(ds)ds.textContent=`Time lock: ${t}s remaining.`;},1000);const dr=document.getElementById('disclosureResult');if(dr)dr.innerHTML='';showToast('Disclosure request opened.');}catch(e){showToast('Error.',false);}}
async function disclosureApprove(id){if(isOffline){showToast('Demo mode.',false);return;}if(!disclosureActive){alert('Open a request first!');return;}try{await fetch(`${API}/api/crypto/disclosure/approve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({trustee_id:id})});const btn=document.getElementById('tb-'+id);if(btn)btn.className='trustee-btn approved';showToast(`Trustee ${id} approved.`);}catch(e){showToast('Error.',false);}}
async function disclosureDecrypt(){if(isOffline){showToast('Demo mode.',false);return;}if(!disclosureActive){alert('Open a request first!');return;}try{const r=await fetch(`${API}/api/crypto/disclosure/decrypt`,{method:'POST'});const d=await r.json();const el=document.getElementById('disclosureResult');if(!el)return;if(d.success){el.style.color='var(--green)';el.innerHTML=`Revealed: ${d.decrypted_identity}`;}else{el.style.color='var(--red)';el.innerHTML=d.reason;}}catch(e){showToast('Error.',false);}}
async function loadRevocation(){if(isOffline)return;try{const r=await fetch(`${API}/api/crypto/revocation`);const d=await r.json();const rr=document.getElementById('revRoot');if(rr)rr.textContent='0x'+d.revocation_root.slice(0,16)+'...';const rl=document.getElementById('revokedList');if(rl)rl.innerHTML=d.revoked_wallets.length?d.revoked_wallets.map(w=>`<div>${w.slice(0,20)}...</div>`).join(''):'None.';}catch(e){}}
async function revokeWallet(){if(isOffline){showToast('Demo mode.',false);return;}const w=document.getElementById('revokeSelect');if(!w||!w.value)return;try{await fetch(`${API}/api/crypto/revocation/revoke`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wallet:w.value})});showToast(`Revoked ${w.value.slice(0,8)}...`);loadRevocation();}catch(e){showToast('Error.',false);}}
async function loadFolding(){if(isOffline)return;try{const r=await fetch(`${API}/api/crypto/folding`);const d=await r.json();const fr=document.getElementById('foldingRoot');if(fr)fr.textContent='0x'+d.accumulator.slice(0,20)+'...';}catch(e){}}
async function foldStep(){if(isOffline){showToast('Demo mode.',false);return;}const w=document.getElementById('foldingWitness');try{await fetch(`${API}/api/crypto/folding/fold`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({witness:w?w.value:''})});showToast('Step folded!');loadFolding();}catch(e){showToast('Error.',false);}}
async function resetFolding(){if(isOffline){showToast('Demo mode.',false);return;}try{await fetch(`${API}/api/crypto/folding/reset`,{method:'POST'});showToast('Accumulator reset.');loadFolding();}catch(e){showToast('Error.',false);}}

// ---- zkML ----
async function runZkmlScore(){const wallet=document.getElementById('zkmlWallet').value.trim();const amount=document.getElementById('zkmlAmount').value||0;if(!wallet){showToast('Enter wallet address',false);return;}try{const r=await fetch(`${API}/api/zkml/score/${wallet}?amount=${amount}`);const d=await r.json();const color=d.risk_level==='HIGH'?'var(--red)':d.risk_level==='MEDIUM'?'var(--amber)':'var(--green)';showResult('zkmlResult',`<div style="font-size:22px;font-weight:700;color:${color}">${(d.risk_score*100).toFixed(1)}% Risk</div><div style="margin-top:4px">Level: <strong style="color:${color}">${d.risk_level}</strong></div><div style="margin-top:4px;font-size:11px;color:var(--text3)">ZK Proof: <span style="font-family:'Courier New',monospace">${d.zk_proof.slice(0,32)}…</span></div>`);showToast(`Risk: ${d.risk_level}`);}catch(e){showResult('zkmlResult','Backend offline','fail');}}
async function runZkmlBatch(){try{const r=await fetch(`${API}/api/zkml/batch-score`);const d=await r.json();const list=document.getElementById('zkmlBatchList');if(!list)return;list.innerHTML=d.scores.map(s=>{const color=s.risk_level==='HIGH'?'var(--red)':s.risk_level==='MEDIUM'?'var(--amber)':'var(--green)';return `<div class="list-item"><div class="item-meta"><div class="item-name">${s.name||s.address.slice(0,20)}</div><div class="item-sub">${s.address.slice(0,24)}…</div></div><div style="flex-shrink:0"><span style="color:${color};font-weight:600">${(s.risk_score*100).toFixed(1)}%</span> <span class="badge b-${s.risk_level==='HIGH'?'blocked':s.risk_level==='MEDIUM'?'gold':'ok'}">${s.risk_level}</span></div></div>`;}).join('');}catch(e){showToast('Error loading batch',false);}}

// ---- SOULBOUND ----
async function issueSoulbound(){const wallet=document.getElementById('cstWallet').value.trim();const jur=document.getElementById('cstJurisdiction').value;const ttl=document.getElementById('cstTtl').value;if(!wallet){showToast('Enter wallet address',false);return;}try{const r=await fetch(`${API}/api/soulbound/issue`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wallet_address:wallet,jurisdiction:jur,ttl_days:parseInt(ttl)})});const d=await r.json();showResult('cstResult',`<strong>Soulbound Token Issued</strong><br>Token ID: <span style="font-family:'Courier New',monospace;font-size:10px">${d.token_id.slice(0,32)}…</span><br>KYC Tier: ${d.kyc_tier} Jurisdiction: ${d.jurisdiction}<br>Expires: ${new Date(d.expires_at*1000).toLocaleDateString()}`,'ok');showToast('CST issued!');loadSoulboundList();}catch(e){showResult('cstResult','Backend offline','fail');}}
async function verifySoulbound(){const wallet=document.getElementById('cstWallet').value.trim();if(!wallet){showToast('Enter wallet address',false);return;}try{const r=await fetch(`${API}/api/soulbound/verify/${wallet}`);const d=await r.json();showResult('cstResult',d.valid?`<strong>Valid CST</strong><br>Tier: ${d.kyc_tier} Jurisdiction: ${d.jurisdiction}<br>Expires in: ${d.expires_in_days} days`:`<strong>${d.reason}</strong>`,d.valid?'ok':'fail');}catch(e){showResult('cstResult','Backend offline','fail');}}
async function loadSoulboundList(){try{const r=await fetch(`${API}/api/soulbound/list`);const d=await r.json();const el=document.getElementById('soulboundList');if(!el)return;el.innerHTML=d.tokens.length===0?'<div style="padding:16px;text-align:center;color:var(--text3);font-size:12px">No tokens issued yet</div>':d.tokens.map(t=>`<div class="list-item"><div class="item-meta"><div class="item-name">${t.wallet_address.slice(0,20)}…</div><div class="item-sub">${t.token_id.slice(0,20)}… | ${t.jurisdiction}</div></div><div style="flex-shrink:0"><span class="badge ${t.revoked?'b-blocked':'b-ok'}">${t.revoked?'Revoked':'Active'}</span> <span class="badge b-tier">Tier ${t.kyc_tier}</span></div></div>`).join('');}catch(e){}}

// ---- JURISDICTION ----
async function checkJurisdiction(){const wallet=document.getElementById('jurWallet').value.trim();const amount=parseFloat(document.getElementById('jurAmount').value)||0;const jur=document.getElementById('jurCode').value;if(!wallet){showToast('Enter wallet address',false);return;}try{const r=await fetch(`${API}/api/jurisdiction/check`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wallet_address:wallet,amount,jurisdiction:jur})});const d=await r.json();const ok=d.compliant;showResult('jurResult',`<strong>${d.regulation}: ${ok?'Compliant':'Non-Compliant'}</strong><br>${d.violations.length?'Violations:<br>'+d.violations.map(v=>'• '+v).join('<br>'):'No violations'}<br>Travel Rule: ${d.travel_rule_triggered?'Triggered':'Not triggered'}`,ok?'ok':'fail');showToast(ok?'Compliant!':'Violations found',ok);}catch(e){showResult('jurResult','Backend offline','fail');}}

// ---- RESERVES ----
async function createSnapshot(){const liabilities=parseFloat(document.getElementById('resLiabilities').value)||0;const reserves=parseFloat(document.getElementById('resReserves').value)||0;try{const r=await fetch(`${API}/api/reserves/snapshot`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({total_liabilities:liabilities,total_reserves:reserves})});const d=await r.json();showResult('reserveResult',`<strong>${d.solvent?'Solvent':'Insolvent'}</strong><br>Reserve Ratio: ${(d.reserve_ratio*100).toFixed(1)}%<br>ZK Commitment: <span style="font-family:'Courier New',monospace;font-size:10px">${d.zk_commitment.slice(0,32)}…</span>`,d.solvent?'ok':'fail');showToast(d.solvent?'Solvency attested!':'Insolvency detected!',d.solvent);loadReserveHistory();}catch(e){showResult('reserveResult','Backend offline','fail');}}
async function loadReserveHistory(){try{const r=await fetch(`${API}/api/reserves/history`);const d=await r.json();const el=document.getElementById('reserveHistoryList');if(!el)return;el.innerHTML=d.snapshots.length===0?'<div style="padding:16px;text-align:center;color:var(--text3);font-size:12px">No snapshots yet</div>':d.snapshots.map(s=>`<div class="list-item"><div class="item-meta"><div class="item-name">${new Date(s.timestamp*1000).toLocaleString()}</div><div class="item-sub">Ratio: ${(s.reserve_ratio*100).toFixed(1)}% | ${s.zk_commitment.slice(0,20)}…</div></div><span class="badge ${s.reserve_ratio>=1?'b-ok':'b-blocked'}" style="flex-shrink:0">${s.reserve_ratio>=1?'Solvent':'Insolvent'}</span></div>`).join('');}catch(e){}}

// ---- ADVANCED ----
async function registerDeadman(){const wallet=document.getElementById('deadmanWallet').value.trim();const amount=parseFloat(document.getElementById('deadmanAmount').value)||0;const interval=parseInt(document.getElementById('deadmanInterval').value)||300;if(!wallet){showToast('Enter wallet address',false);return;}try{const r=await fetch(`${API}/api/deadman/register`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wallet_address:wallet,unlock_amount:amount,heartbeat_interval:interval,beneficiary:wallet})});const d=await r.json();showResult('deadmanResult',`<strong>Deadman Switch Registered</strong><br>${d.note}`);showToast('Registered!');}catch(e){showResult('deadmanResult','Backend offline','fail');}}
async function sendHeartbeat(){const wallet=document.getElementById('deadmanWallet').value.trim();if(!wallet){showToast('Enter wallet',false);return;}try{await fetch(`${API}/api/deadman/heartbeat/${wallet}`,{method:'POST'});showToast('Heartbeat sent!');}catch(e){showToast('Error',false);}}
async function checkDeadman(){const wallet=document.getElementById('deadmanWallet').value.trim();if(!wallet){showToast('Enter wallet',false);return;}try{const r=await fetch(`${API}/api/deadman/status/${wallet}`);const d=await r.json();showResult('deadmanResult',`Status: <strong style="color:${d.triggered?'var(--red)':'var(--green)'}">${d.triggered?'Triggered':'Active'}</strong><br>Silent for: ${d.silent_for_seconds}s / ${d.threshold_seconds}s<br>Unlock: $${d.unlock_amount}`);}catch(e){showResult('deadmanResult','Not registered or offline','fail');}}
async function linkKycTree(){const parent=document.getElementById('kycParent').value.trim();const child=document.getElementById('kycChild').value.trim();if(!parent||!child){showToast('Enter both wallets',false);return;}try{const r=await fetch(`${API}/api/kyc-tree/link`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({parent_wallet:parent,child_wallet:child})});const d=await r.json();showResult('kycTreeResult',`<strong>Linked</strong><br>Inherited KYC Tier: ${d.inherited_kyc_tier}<br>Tree Depth: ${d.inheritance_depth}`,'ok');showToast('KYC inheritance linked!');}catch(e){showResult('kycTreeResult','Backend offline','fail');}}
async function resolveKycInheritance(){const wallet=document.getElementById('kycChild').value.trim()||document.getElementById('kycParent').value.trim();if(!wallet){showToast('Enter wallet',false);return;}try{const r=await fetch(`${API}/api/kyc-tree/resolve/${wallet}`);const d=await r.json();showResult('kycTreeResult',`KYC Tier: <strong>${d.kyc_tier}</strong><br>Source: ${d.source}${d.inherited?' (inherited)':''}`,d.kyc_tier>0?'ok':'fail');}catch(e){showResult('kycTreeResult','Error','fail');}}
async function runCanaryScan(){try{const r=await fetch(`${API}/api/canary/scan`);const d=await r.json();showResult('canaryResult',`Scanned ${d.scanned} wallets. Auto-frozen: <strong>${d.auto_frozen.length}</strong>${d.auto_frozen.length?'<br>'+d.auto_frozen.map(f=>`• ${f.wallet.slice(0,20)}… (${(f.risk_score*100).toFixed(0)}% risk)`).join('<br>'):''}`,d.auto_frozen.length===0?'ok':'fail');showToast(`Scan complete. ${d.auto_frozen.length} frozen.`,d.auto_frozen.length===0);loadCanaryFreezes();}catch(e){showResult('canaryResult','Backend offline','fail');}}
async function loadCanaryFreezes(){try{const r=await fetch(`${API}/api/canary/freezes`);const d=await r.json();const list=document.getElementById('canaryList');if(!list)return;list.innerHTML=d.freezes.length===0?'':d.freezes.map(f=>`<div class="list-item"><div class="item-meta"><div class="item-name">${f.wallet.slice(0,24)}…</div><div class="item-sub">Risk: ${(f.risk_score*100).toFixed(0)}% · ${new Date(f.frozen_at*1000).toLocaleString()}</div></div><span class="badge b-blocked" style="flex-shrink:0">Frozen ${f.contest_hours_remaining}h left</span></div>`).join('');}catch(e){}}
async function submitWhistleblower(){const complaint=document.getElementById('wbComplaint').value.trim();const subject=document.getElementById('wbSubject').value.trim();const severity=document.getElementById('wbSeverity').value;if(!complaint){showToast('Enter a complaint.',false);return;}try{const r=await fetch(`${API}/api/whistleblower/submit`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({complaint,subject_wallet:subject||null,severity})});const d=await r.json();showResult('wbResult',`<strong>Submitted Anonymously</strong><br>Receipt: <span style="font-family:'Courier New',monospace;font-size:10px">${d.receipt_hash.slice(0,32)}…</span><br>Your identity is protected.`,'ok');showToast('Submitted anonymously.');document.getElementById('wbComplaint').value='';}catch(e){showResult('wbResult','Backend offline','fail');}}
async function issueTimedProof(){const wallet=document.getElementById('timedWallet').value.trim();const type=document.getElementById('timedType').value;const ttl=parseInt(document.getElementById('timedTtl').value)||24;if(!wallet){showToast('Enter wallet address.',false);return;}try{const r=await fetch(`${API}/api/timed-proofs/issue`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wallet_address:wallet,proof_type:type,ttl_hours:ttl})});const d=await r.json();showResult('timedResult',`<strong>Proof Issued</strong><br>Type: ${d.proof_type}<br>Expires: ${new Date(d.expires_at*1000).toLocaleString()}<br>ID: <span style="font-family:'Courier New',monospace;font-size:10px">${d.proof_id.slice(0,32)}…</span>`,'ok');showToast('Timed proof issued!');}catch(e){showResult('timedResult','Backend offline','fail');}}
async function verifyTimedProof(){const wallet=document.getElementById('timedWallet').value.trim();const type=document.getElementById('timedType').value;if(!wallet){showToast('Enter wallet address.',false);return;}try{const r=await fetch(`${API}/api/timed-proofs/verify/${wallet}?proof_type=${type}`);const d=await r.json();showResult('timedResult',d.valid?`<strong>Valid Proof</strong><br>Expires in: ${d.expires_in_hours}h<br>Type: ${d.proof_type}`:`<strong>Invalid:</strong> ${d.reason}`,d.valid?'ok':'fail');}catch(e){showResult('timedResult','Backend offline','fail');}}
async function createBridgeAttestation(){const wallet=document.getElementById('bridgeWallet').value.trim();const anchor=document.getElementById('bridgeAnchor').value;if(!wallet){showToast('Enter wallet address.',false);return;}try{const r=await fetch(`${API}/api/bridge-attestation/create`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wallet_address:wallet,target_anchor:anchor})});const d=await r.json();showResult('bridgeResult',`<strong>Bridge Attestation Created</strong><br>Anchor: ${d.target_anchor}<br>KYC Tier: ${d.kyc_tier}<br>ID: <span style="font-family:'Courier New',monospace;font-size:10px">${d.attestation_id.slice(0,32)}…</span>`,'ok');showToast('Attestation created!');}catch(e){showResult('bridgeResult','Backend offline','fail');}}

// ---- CIRCUIT NODES SETUP ----
(function buildCircuit(){
  const container=document.getElementById('circuitNodes');if(!container)return;
  const STEPS2=['rev','san','kyc','lim','proof'];
  STEPS2.forEach((id,i)=>{
    const node=document.createElement('div');node.className='cn';node.id='cn-'+id;container.appendChild(node);
    if(i<STEPS2.length-1){
      const line=document.createElement('div');line.style.cssText='flex:1;height:1px;background:rgba(99,102,241,.15)';
      container.appendChild(line);
    }
  });
})();

// ---- INIT ----
document.addEventListener('DOMContentLoaded',()=>{
  loadRules();
  loadWallets();
  setTimeout(loadAuditLogs,800);
});
window.addEventListener('click',(e)=>{
  const modal=document.getElementById('walletModal');
  if(e.target===modal)closeWalletModal();
});
document.addEventListener('keydown',(e)=>{
  if(e.key==='Enter'&&e.shiftKey&&document.getElementById('panel-core')&&document.getElementById('panel-core').classList.contains('active')){
    runSimulation();
  }
});
