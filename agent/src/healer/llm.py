"""LLM brain: evidence + retrieved runbooks (RAG) -> structured JSON fix plan.
Same output format as the rules brain, so the rest of the agent doesn't care which brain ran."""
import json, os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".env"))
MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
API_KEY = os.getenv("GROQ_API_KEY", "")
ACTIONS = ["attach_configmap", "increase_memory_limit", "rollback", "rightsize", "escalate"]

SYSTEM_PROMPT = f"""You are a careful Site Reliability Engineer agent for Kubernetes.
Diagnose the failure using the EVIDENCE and the RUNBOOKS. Respond with ONLY a JSON object with keys:
  "root_cause": one sentence,
  "action": one of {ACTIONS},
  "params": object (for attach_configmap: {{"configmap": "<exact name from evidence>"}}),
  "risk": "low" | "medium" | "high",
  "confidence": number between 0 and 1,
  "reasoning": max 2 sentences citing the evidence and the runbook.
Rules: only propose actions the runbooks support. Never invent ConfigMap names, values or secrets.
If the evidence is unclear or no runbook fits, use action "escalate"."""

def _escalate(why: str) -> dict:
    return {"root_cause": why, "action": "escalate", "params": {}, "risk": "high",
            "confidence": 0.0, "reasoning": why}

def validate(plan: dict, ev: dict) -> dict:
    """Never trust LLM output blindly: check it against reality before the guardrails even see it."""
    if plan.get("action") not in ACTIONS:
        return _escalate(f"LLM proposed unknown action {plan.get('action')!r}")
    if plan.get("risk") not in ("low", "medium", "high"):
        plan["risk"] = "high"
    try:
        plan["confidence"] = float(plan.get("confidence", 0))
    except (TypeError, ValueError):
        plan["confidence"] = 0.0
    plan.setdefault("params", {})
    if plan["action"] == "attach_configmap" and plan["params"].get("configmap") not in ev["configmaps"]:
        return _escalate(f"Hallucination blocked: ConfigMap {plan['params'].get('configmap')!r} does not exist")
    return plan

def diagnose(ev: dict, knowledge: list[dict]) -> dict:
    evidence = {k: ev[k] for k in ("reason", "restarts", "deployment", "logs", "configmaps")}
    user_msg = ("EVIDENCE:\n" + json.dumps(evidence, indent=1) +
                "\n\nRUNBOOKS AND PAST INCIDENTS (most relevant first):\n" +
                "\n---\n".join(d["text"] for d in knowledge))
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                      headers={"Authorization": f"Bearer {API_KEY}"},
                      json={"model": MODEL, "temperature": 0,
                            "response_format": {"type": "json_object"},
                            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                         {"role": "user", "content": user_msg}]},
                      timeout=60)
    r.raise_for_status()
    data = r.json()
    plan = validate(json.loads(data["choices"][0]["message"]["content"]), ev)
    plan["brain"] = f"llm:{MODEL}"
    plan["tokens"] = data.get("usage", {}).get("total_tokens")
    plan["rag_sources"] = [d["source"] for d in knowledge]
    return plan
