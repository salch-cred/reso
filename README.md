---
title: Reso
emoji: 🔒
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Reso — Privacy-Preserving Compliance Engine on Stellar

ZK-native compliance infrastructure built on Stellar Protocol 25.

## Live

- **App Console**: [reso-nine.vercel.app](https://reso-nine.vercel.app)
- **Landing page**: [reso-nine.vercel.app/landing](https://reso-nine.vercel.app/landing)
- **Docs**: [reso-nine.vercel.app/docs](https://reso-nine.vercel.app/docs)
- **API (HF Space)**: [salmanch123-reso.hf.space](https://salmanch123-reso.hf.space)

## Stack

- **Frontend**: Vanilla HTML/CSS/JS on Vercel
- **Backend**: FastAPI + SQLite on Hugging Face Spaces (Docker)
- **Blockchain**: Stellar Testnet / Soroban

## Features

1. ZK-Proof Transaction Simulator
2. FHE Spending Limits (Paillier)
3. Threshold + Time-Locked Identity Disclosure (Shamir 3-of-5)
4. Real-Time Credential Revocation (Merkle)
5. Recursive Proof Folding (Nova-style IVC)
6. ZK-Gated Claimable Balance Escrow
7. SEP-8 Regulated Asset Approval
8. SEP-12 Anchor KYC Bridge
9. Clawback-Triggered Revocation

## Run Locally

```bash
pip install -r requirements.txt
uvicorn oracle.main:app --host 0.0.0.0 --port 8000
```
