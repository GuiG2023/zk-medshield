"""
ZK-MedShield 后端网关 (Hackathon PoC)
--------------------------------------
数据流: 前端 JSON -> 本地脱敏 -> 本地 ZK 证明(血糖是否偏高) -> Gemini 生成调理建议

运行前:
    pip install fastapi uvicorn "google-genai" --break-system-packages
    export GEMINI_API_KEY=你的key
    uvicorn main:app --reload

USE_MOCK_PROOF=true (默认) 时,ZK 那一步不依赖 Docker/Node/proof-server 是否搭好,
方便你今天先把 FastAPI + Gemini 这半条链路跑通、录 demo 视频的脚本走一遍。
等 Compact 合约 + Node 那边真的调通了,把环境变量设成 false 即可切换到真实证明。
"""
import os
import re
import json
import subprocess
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google import genai

app = FastAPI(title="ZK-MedShield")

USE_MOCK_PROOF = os.getenv("USE_MOCK_PROOF", "true").lower() == "true"

# 极简 PII 脱敏规则 —— PoC 够用,生产环境需要更严谨的方案
ID_NUMBER_RE = re.compile(r"\b\d{15}(\d{2}[0-9Xx])?\b")
RECORD_NO_RE = re.compile(r"病历号[:：]?\s*\S+")


class LabReport(BaseModel):
    patient_name: Optional[str] = None
    id_number: Optional[str] = None
    record_number: Optional[str] = None
    fasting_glucose_mgdl: float  # 唯一进入 ZK 电路的敏感数值,绝不转发给 Gemini


def redact(report: LabReport) -> dict:
    """在离开这个进程之前,先把直接身份标识全部剥离。"""
    return {"fasting_glucose_mgdl": report.fasting_glucose_mgdl}


def run_zk_proof(glucose_value: float) -> dict:
    """
    调用 Compact 电路,拿到一个"是否高风险"的布尔结论 + 对应的 ZK 证明,
    过程中原始 glucose_value 不会被转发到下游。

    真实路径(Phase 1/2 的 Node 侧跑通后):
        subprocess.run(["node", "prove.js", str(glucose_value)], ...)
        prove.js 负责加载 compact compile 生成的 managed/blood_glucose/ 产物,
        把 glucose_value 作为 witness 喂给电路,按需再和本地 proof server
        (localhost:6300) 交互产出真实 proof。
        这部分 TS 胶水代码建议直接抄改自官方 example-hello-world 仓库里的
        测试脚本,而不是手写 —— 那是官方验证过能跑的参考实现。

    MOCK 路径:直接复刻 Compact 电路里同样的判断逻辑(> 100),
    保证后端其余部分今天就能被完整测试。
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


GEMINI_PROMPT_TEMPLATE = """你是一名健康顾问助手。你收到的是【经零知识证明验证过的结论】,而不是原始检验数值:

- 指标类型: 空腹血糖 (Fasting Blood Glucose)
- 验证结论: {status_text}
- 结论来源: 本地 Compact 智能合约生成的零知识证明,已在本地验证通过;
  你不会、也不需要看到具体的血糖数值。

请只依据上面这条"验证结论"作答,不要猜测或编造具体数字,给出:
1. 该结论对应的通俗解释(1-2 句)
2. 3 条日常生活方式/饮食调理建议
3. 一句提醒:本建议不能替代医生诊断,如有不适请及时就医
"""

client = genai.Client()  # 自动从环境变量 GEMINI_API_KEY 读取密钥


@app.post("/api/analyze-report")
async def analyze_report(report: LabReport):
    redacted = redact(report)

    try:
        proof_result = run_zk_proof(redacted["fasting_glucose_mgdl"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ZK proof 步骤失败: {e}")

    status_text = (
        "血糖偏高风险 (>100 mg/dL)"
        if proof_result["is_high_risk"]
        else "血糖在正常范围 (70-100 mg/dL)"
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
