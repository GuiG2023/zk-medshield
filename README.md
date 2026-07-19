# ZK-MedShield

**Using Midnight's rational privacy to redact medical lab data with Zero-Knowledge Proofs before it is analyzed by AI — you yield conclusions, not numbers.**

> Midnight Hackathon 2026 Submission

---

## Why We Built This

Hospitals, health checkup institutions, and wearable device manufacturers all want to use AI to help users interpret health data. However, there is a realistic compliance conflict: feeding raw lab values (blood glucose, blood pressure, etc.) directly into a third-party LLM API means these sensitive data leave the local device and enter third-party systems outside your control.

Traditional "redaction" methods (hiding names, deleting IDs) only solve the identity identifier issue, but **do not solve the fact that the values themselves are still in plaintext**. ZK-MedShield explores another path: can we let AI only see the "conclusion" instead of the "numbers", and have this conclusion be mathematically verifiable rather than arbitrarily guessed?

## What Midnight Solves

The data model of standard blockchains is "fully public"; traditional privacy coins (like Monero) are "fully hidden". Midnight positions itself in between: **"rational privacy"** — where developers control exactly what granularity of data is disclosed. Disclosed data is backed by a zero-knowledge proof, while undisclosed data remains strictly local forever.

This concept manifests as a compiler-enforced rule in the Compact language: **any value derived from a `witness` (private input) must be explicitly wrapped in `disclose()` to be output from a circuit or written to the ledger state; otherwise, it fails to compile.** The official documentation refers to this design as the "Witness Protection Program" — you cannot "accidentally" leak a private value; the compiler blocks you the moment you attempt to do so.

Our circuit is a Minimal Viable Example (MVE) of this concept:

```compact
pragma language_version 0.23;

import CompactStandardLibrary;

export ledger isHigh: Boolean;

witness fastingGlucose(): Uint<16>;

export circuit isHighRisk(): [] {
  isHigh = disclose(fastingGlucose() > 100);
}
```

- `fastingGlucose()` — The user's actual fasting blood glucose value, which only exists locally. It never goes on-chain, is not included in the proof transcript, and is never sent to any API.
- `isHigh` — The only disclosed state: whether it is in the high-risk range (>100 mg/dL). This disclosure is **actively declared by the developer**, not a default behavior.

## Data Flow

```
User inputs lab metrics (local)
            │
            ▼
Local redaction (strips direct identifiers like names/IDs)
            │
            ▼
Compact circuit generates ZK proof locally (glucose value → boolean conclusion; raw value remains local)
            │
            ▼
"Conclusion + ZK Proof" submitted to Gemini API
            │
            ▼
Gemini generates personalized health recommendations without raw values ever leaving the user's local device
```

## Tech Stack

| Component | Technology |
|---|---|
| ZK Circuit | Midnight / Compact 0.23 |
| Proof Generation | Local Proof Server (Docker) |
| Backend Gateway | Python / FastAPI |
| Recommendation | Gemini API (`gemini-3.5-flash`) |

## Verified Technical Outputs

This is not just a block diagram on a whiteboard — the following are actual verified outputs ran on our local machines:

- Compiled successfully via `compact compile`. In `contract-info.json`, `"proof": true` and the `ledger` array contains `isHigh`.
- Real proving/verifying keys have been generated: `isHighRisk.prover` (147 KB) and `isHighRisk.verifier` (1 KB). This steep ratio in file sizes is a typical signature of ZK-SNARK proving/verifying key structures (proving keys contain the full constraint system, while verifying keys only require a minimal set of public parameters).
- In the local devnet environment of the official `example-hello-world` starter repo, we successfully ran the complete witness-to-proof generation pipeline for two test cases: glucose of 105 (resolves to high-risk: true) and 85 (resolves to high-risk: false).

## Running Locally

See `SETUP.md` for details. Core commands:

```bash
# 1. Install Compact toolchain + run local proof server
curl --proto '=https' --tlsv1.2 -LsSf https://github.com/midnightntwrk/compact/releases/latest/download/compact-installer.sh | sh
docker run -p 6300:6300 midnightntwrk/proof-server:latest midnight-proof-server -v

# 2. Compile circuit
compact compile blood_glucose_ledger.compact managed/blood_glucose

# 3. Start backend (mock mode; runs independently of the above steps)
pip install fastapi uvicorn "google-genai" --break-system-packages
export GEMINI_API_KEY=your_key
uvicorn main:app --reload
```

## Project Status & Next Steps

Honest statement of current completion (instead of masking it as "fully connected"):

- ✅ Compact circuit design, compilation, and real ZK proof generation — verified and working.
- ✅ FastAPI + Gemini gateway — working (currently in mock mode, replicating the circuit's risk evaluation logic for easy, independent testing).
- 🔜 **Next Step**: Connect the real-time proof-server pipeline directly inside the Python gateway (currently, proof generation was verified independently via `example-hello-world`'s test suite, but has not yet been integrated into the `/api/analyze-report` real-time request pathway).
- 🔜 Multi-metric aggregate risk evaluation, Merkle tree member credentials proof (advanced selective disclosure).

## AI Attribution

As per MLH Hackathon rules, we fully declare the use of AI tools during development:

- **Claude** (Anthropic) — Assisted in requirement definitions, architecture design, verifying Midnight/Compact official documentation, and code reviews.
- **Antigravity** — Assisted in local environment setup, code execution, compilation, and testing.
- **Gemini API** (`gemini-3.5-flash`) — Integrated as a functional component of the product to generate the health recommendations (not used as a development assistant, but rather as part of the application runtime).

## Disclaimer

This project is a hackathon Proof of Concept (PoC). The generated health suggestions are for reference only and cannot replace professional medical diagnosis. Consult a physician for any health issues.
