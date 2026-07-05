// ====================================================
// REMAINING API FUNCTIONS + INIT
// ====================================================

async function loadCanaryFreezes(){
  try{
    const r=await fetch(`${API}/api/canary/freezes`);
    const d=await r.json();
    const list=document.getElementById('canaryList');
    list.innerHTML=d.freezes.length===0?'':
      d.freezes.map(f=>`<div class="list-item"><div class="item-meta"><div class="item-name">${f.wallet.slice(0,24)}&hellip;</div><div class="item-sub">Risk: ${(f.risk_score*100).toFixed(0)}% &nbsp;&middot;&nbsp; ${new Date(f.frozen_at*1000).toLocaleString()}</div></div><span class="badge b-blocked" style="flex-shrink:0">Frozen ${f.contest_hours_remaining}h left</span></div>`).join('');
  }catch(e){}
}

async function submitWhistleblower(){
  const complaint=document.getElementById('wbComplaint').value.trim();
  const subject=document.getElementById('wbSubject').value.trim();
  const severity=document.getElementById('wbSeverity').value;
  if(!complaint){showToast('Enter a complaint.',false);return;}
  try{
    const r=await fetch(`${API}/api/whistleblower/submit`,{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({complaint,subject_wallet:subject||null,severity})});
    const d=await r.json();
    showResult('wbResult',`<strong>Submitted Anonymously</strong><br>Receipt: <span style="font-family:'Courier New',monospace;font-size:10px">${d.receipt_hash.slice(0,32)}&hellip;</span><br>Your identity is fully protected.`,'ok');
    showToast('Complaint submitted anonymously.');
    document.getElementById('wbComplaint').value='';
  }catch(e){showResult('wbResult','Backend offline','fail');}
}

async function issueTimedProof(){
  const wallet=document.getElementById('timedWallet').value.trim();
  const type=document.getElementById('timedType').value;
  const ttl=parseInt(document.getElementById('timedTtl').value)||24;
  if(!wallet){showToast('Enter wallet address.',false);return;}
  try{
    const r=await fetch(`${API}/api/timed-proofs/issue`,{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({wallet_address:wallet,proof_type:type,ttl_hours:ttl})});
    const d=await r.json();
    showResult('timedResult',`<strong>Proof Issued</strong><br>Type: ${d.proof_type}<br>Expires: ${new Date(d.expires_at*1000).toLocaleString()}<br>ID: <span style="font-family:'Courier New',monospace;font-size:10px">${d.proof_id.slice(0,32)}&hellip;</span>`,'ok');
    showToast('Timed proof issued!');
  }catch(e){showResult('timedResult','Backend offline','fail');}
}

async function verifyTimedProof(){
  const wallet=document.getElementById('timedWallet').value.trim();
  const type=document.getElementById('timedType').value;
  if(!wallet){showToast('Enter wallet address.',false);return;}
  try{
    const r=await fetch(`${API}/api/timed-proofs/verify/${wallet}?proof_type=${type}`);
    const d=await r.json();
    showResult('timedResult',d.valid?
      `<strong>Valid Proof</strong><br>Expires in: ${d.expires_in_hours}h<br>Type: ${d.proof_type}`:
      `<strong>Invalid:</strong> ${d.reason}`,
      d.valid?'ok':'fail');
  }catch(e){showResult('timedResult','Backend offline','fail');}
}

async function createBridgeAttestation(){
  const wallet=document.getElementById('bridgeWallet').value.trim();
  const anchor=document.getElementById('bridgeAnchor').value;
  if(!wallet){showToast('Enter wallet address.',false);return;}
  try{
    const r=await fetch(`${API}/api/bridge-attestation/create`,{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({wallet_address:wallet,target_anchor:anchor})});
    const d=await r.json();
    showResult('bridgeResult',`<strong>Bridge Attestation Created</strong><br>Anchor: ${d.target_anchor}<br>KYC Tier: ${d.kyc_tier}<br>Attestation ID: <span style="font-family:'Courier New',monospace;font-size:10px">${d.attestation_id.slice(0,32)}&hellip;</span>`,'ok');
    showToast('Bridge attestation created!');
  }catch(e){showResult('bridgeResult','Backend offline','fail');}
}

// ====================================================
// INIT
// ====================================================
document.addEventListener('DOMContentLoaded',()=>{
  loadRules();
  loadWallets();
  setTimeout(loadAuditLogs,800);
});

window.addEventListener('click',(e)=>{
  const modal=document.getElementById('walletModal');
  if(e.target===modal)closeWalletModal();
});

// keyboard shortcut: G+P = generate proof
document.addEventListener('keydown',(e)=>{
  if(e.key==='Enter'&&e.shiftKey&&document.getElementById('panel-core').classList.contains('active')){
    runSimulation();
  }
});
