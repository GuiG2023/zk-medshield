"""
ZK-MedShield Backend Gateway (Hackathon PoC)
--------------------------------------------
Data Flow: Frontend JSON -> Local Redaction -> Local ZK Proof (Is glucose high?) -> Gemini Health Advice

Before Running:
    pip install fastapi uvicorn "google-genai" --break-system-packages
    export GEMINI_API_KEY=your_key
    uvicorn main:app --reload

When USE_MOCK_PROOF=true (default), the ZK step does not depend on Docker/Node/proof-server.
This allows you to test the FastAPI + Gemini pipeline first and run the demo video script.
Once the Compact contract + Node wrapper are functional, set this environment variable to false to switch to real proofs.
"""
import os
import re
import json
import subprocess
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai

app = FastAPI(title="ZK-MedShield")

# For Demo: allows the browser to open index.html directly (via file:// or any local port) to call this API.
# In production, allow_origins=["*"] should not be used. This is a hackathon PoC for speed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

USE_MOCK_PROOF = os.getenv("USE_MOCK_PROOF", "true").lower() == "true"

# Simple PII redaction rules — sufficient for PoC, production needs a more robust solution
ID_NUMBER_RE = re.compile(r"\b\d{15}(\d{2}[0-9Xx])?\b")
RECORD_NO_RE = re.compile(r"病历号[:：]?\s*\S+")


class LabReport(BaseModel):
    patient_name: Optional[str] = None
    id_number: Optional[str] = None
    record_number: Optional[str] = None
    fasting_glucose_mgdl: float  # The only sensitive value entering the ZK circuit, never forwarded to Gemini


def redact(report: LabReport) -> dict:
    """Strips direct identifiers before the data leaves the process."""
    return {"fasting_glucose_mgdl": report.fasting_glucose_mgdl}


def run_zk_proof(glucose_value: float) -> dict:
    """
    Calls the Compact circuit to get a boolean conclusion "is_high_risk" + ZK proof.
    The raw glucose_value is never forwarded downstream.

    Real path (after Phase 1/2 Node.js setup is functional):
        subprocess.run(["node", "prove.js", str(glucose_value)], ...)
        prove.js is responsible for loading the compact compile output generated in managed/blood_glucose/,
        feeding glucose_value as a witness to the circuit, and communicating with the local proof server
        (localhost:6300) to output the real proof.
        This TS glue code should be adapted from the test scripts in the official example-hello-world repo
        rather than written from scratch, as it is a verified reference implementation.

    MOCK path: replicates the same evaluation logic (> 100) as the Compact circuit,
    ensuring the rest of the backend can be fully tested immediately.
    """
    if USE_MOCK_PROOF:
        return {
            "is_high_risk": glucose_value > 100,
            "proof": "MOCK-PROOF-NOT-REAL",
            "verified": True,
        }

    result = subprocess.run(
        ["node", "prove.js", str(glucose_value)],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


GEMINI_PROMPT_TEMPLATE = """You are a health advisor assistant. You receive a [conclusion verified via Zero-Knowledge Proof] instead of the raw laboratory values:

- Metric Type: Fasting Blood Glucose
- Verification Conclusion: {status_text}
- Conclusion Source: A Zero-Knowledge Proof generated locally by a Compact smart contract, verified locally;
  you do not see, nor do you need to see, the actual blood glucose values.

Please answer based ONLY on the "Verification Conclusion" above. Do not guess or fabricate specific numbers. Provide:
1. A lay explanation of the conclusion (1-2 sentences)
2. 3 daily lifestyle / dietary recommendation tips
3. A reminder: This advice does not replace professional medical diagnosis. Consult a physician for any health issues.
"""

client = genai.Client()  # Automatically reads the API key from GEMINI_API_KEY environment variable


@app.post("/api/analyze-report")
async def analyze_report(report: LabReport):
    redacted = redact(report)

    try:
        proof_result = run_zk_proof(redacted["fasting_glucose_mgdl"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ZK proof step failed: {e}")

    status_text = (
        "High blood glucose risk (>100 mg/dL)"
        if proof_result["is_high_risk"]
        else "Blood glucose in normal range (70-100 mg/dL)"
    )

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=GEMINI_PROMPT_TEMPLATE.format(status_text=status_text),
    )

    return {
        "is_high_risk": proof_result["is_high_risk"],
        "proof_verified": proof_result["verified"],
        "proof_mode": "mock" if USE_MOCK_PROOF else "real",
        "advice": response.text,
    }
