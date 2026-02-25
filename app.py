from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

load_dotenv()

app = FastAPI(title="Chenbanxian Middleware", version="0.3.0")

ZIWEI_KEYWORDS = [
    "紫微",
    "斗数",
    "命盘",
    "四化",
    "星曜",
    "宫位",
    "流年",
    "大限",
    "三方四正",
    "化禄",
    "化权",
    "化科",
    "化忌",
]


# --------------------------
# ENV helpers
# --------------------------
def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return float(v)
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return int(v)
    except Exception:
        return default


# --------------------------
# Request/Response models
# --------------------------
class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    chat_type: Literal["private", "group"] = "private"
    addressed: bool = True
    force: bool = False


class AskResponse(BaseModel):
    should_answer: bool
    uncertain: bool = False
    reason: str | None = None
    mode: Literal["ziweidoushu-kb", "direct-llm", "reject"]
    retrieval_params: dict[str, Any] | None = None
    answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    raw_hits: int = 0


# --------------------------
# Upstream clients
# --------------------------
class NotebookClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OPEN_NOTEBOOK_BASE_URL", "http://127.0.0.1:5055").rstrip("/")
        self.search_path = os.getenv("OPEN_NOTEBOOK_SEARCH_PATH", "/api/search")
        self.timeout = _env_float("OPEN_NOTEBOOK_TIMEOUT_SECONDS", 25)

    async def search(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{self.search_path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r.json()


class LLMClient:
    def __init__(self) -> None:
        self.enabled = _env_bool("ENABLE_LLM", True)
        self.base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "gpt-5.3-codex")
        self.timeout = _env_float("LLM_TIMEOUT_SECONDS", 40)

    async def chat(self, *, system: str, user: str, temperature: float = 0.4) -> str:
        if not self.enabled:
            raise RuntimeError("llm_disabled")
        if not self.base_url:
            raise RuntimeError("llm_base_url_missing")

        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("llm_empty_choices")

        msg = (choices[0] or {}).get("message") or {}
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("llm_empty_content")
        return content.strip()


notebook = NotebookClient()
llm = LLMClient()


# --------------------------
# Core logic
# --------------------------
def is_ziweidoushu_intent(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ZIWEI_KEYWORDS)


def build_answer_policy() -> str:
    # 统一“非模板化”约束，不允许固定填空结构
    return (
        "回答必须自然对话化，禁止使用固定模板标题（如‘结论：/依据：/建议：’）。"
        "可以分段，但不要机械套格式。"
    )


def build_retrieval_params(question: str) -> dict[str, Any]:
    params = {
        "type": os.getenv("BASELINE_SEARCH_TYPE", "vector"),
        "limit": _env_int("BASELINE_LIMIT", 8),
        "minimum_score": _env_float("BASELINE_MIN_SCORE", 0.58),
        "search_sources": _env_bool("BASELINE_SEARCH_SOURCES", True),
        "search_notes": _env_bool("BASELINE_SEARCH_NOTES", False),
    }

    q = question.strip()
    if len(q) <= 8:
        params["limit"] = min(int(params["limit"]), 6)
        params["minimum_score"] = max(float(params["minimum_score"]), 0.62)

    return params


def normalize_hits(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        for key in ("results", "items", "data", "hits"):
            v = raw.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def hit_score(hit: dict[str, Any]) -> float:
    for k in ("score", "similarity", "relevance"):
        v = hit.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def extract_citation(hit: dict[str, Any], idx: int) -> str:
    title = hit.get("title") or hit.get("source") or hit.get("document") or f"证据{idx}"
    page = hit.get("page")
    score = hit_score(hit)
    if page is not None:
        return f"{title} (p.{page}, score={score:.3f})"
    return f"{title} (score={score:.3f})"


def pick_evidence(hits: list[dict[str, Any]], min_score: float) -> tuple[list[dict[str, Any]], list[str]]:
    strong = [h for h in hits if hit_score(h) >= min_score]
    citations = [extract_citation(h, i + 1) for i, h in enumerate(strong[:5])]
    return strong, citations


async def answer_direct_llm(question: str) -> str:
    system = (
        "你是陈半仙。保持自然、口语化、非模板化输出。"
        f"{build_answer_policy()}"
        "不要编造具体命盘事实；若信息不足，明确说明不确定并给出下一步提问建议。"
    )
    user = f"用户问题：{question}"
    return await llm.chat(system=system, user=user, temperature=0.5)


async def answer_ziweidoushu_with_kb(question: str, evidence_hits: list[dict[str, Any]], citations: list[str]) -> str:
    snippets: list[str] = []
    for h in evidence_hits[:5]:
        txt = h.get("content") or h.get("text") or h.get("snippet") or ""
        txt = str(txt).replace("\n", " ").strip()
        if txt:
            snippets.append(txt[:220])

    evidence_block = "\n".join(f"- {s}" for s in snippets) if snippets else "- （无可用片段）"
    cite_block = "\n".join(f"- {c}" for c in citations) if citations else "- （无）"

    system = (
        "你是陈半仙。请根据证据回答紫微斗数问题。"
        "输出要自然、非模板化、像真人对话，不要机械套话。"
        f"{build_answer_policy()}"
        "严禁超出证据硬编；若证据不足，要直接说不确定。"
    )

    user = (
        f"用户问题：{question}\n\n"
        f"检索证据片段：\n{evidence_block}\n\n"
        f"可用引用：\n{cite_block}\n\n"
        "请给出最终回答。"
    )

    return await llm.chat(system=system, user=user, temperature=0.35)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "0.3.0",
        "open_notebook": notebook.base_url,
        "search_path": notebook.search_path,
        "llm_enabled": llm.enabled,
        "group_require_addressed": _env_bool("GROUP_REQUIRE_ADDRESSED", True),
    }


@app.get("/preflight")
async def preflight() -> dict[str, Any]:
    checks: dict[str, Any] = {
        "open_notebook": {"ok": False, "detail": ""},
        "llm": {"ok": False, "detail": ""},
    }

    # Open Notebook connectivity
    try:
        url = f"{notebook.base_url}/health"
        async with httpx.AsyncClient(timeout=min(notebook.timeout, 8)) as client:
            r = await client.get(url)
        checks["open_notebook"] = {
            "ok": r.status_code < 500,
            "detail": f"status={r.status_code}",
        }
    except Exception as e:
        checks["open_notebook"] = {"ok": False, "detail": type(e).__name__}

    # LLM connectivity (minimal)
    if llm.enabled and llm.base_url:
        try:
            test_payload = {
                "model": llm.model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            }
            headers = {"Content-Type": "application/json"}
            if llm.api_key:
                headers["Authorization"] = f"Bearer {llm.api_key}"
            async with httpx.AsyncClient(timeout=min(llm.timeout, 8)) as client:
                r = await client.post(f"{llm.base_url}/chat/completions", headers=headers, json=test_payload)
            checks["llm"] = {"ok": r.status_code < 500, "detail": f"status={r.status_code}"}
        except Exception as e:
            checks["llm"] = {"ok": False, "detail": type(e).__name__}
    else:
        checks["llm"] = {"ok": False, "detail": "disabled_or_missing_base_url"}

    overall = checks["open_notebook"]["ok"] and checks["llm"]["ok"]
    return {"ok": overall, "checks": checks}


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    question = req.question.strip()

    # Group gate
    if not req.force and req.chat_type == "group" and _env_bool("GROUP_REQUIRE_ADDRESSED", True) and not req.addressed:
        return AskResponse(
            should_answer=False,
            mode="reject",
            reason="group_not_addressed",
        )

    ziwei = is_ziweidoushu_intent(question)

    # Route A: non-ziwei -> direct LLM (no search)
    if not ziwei:
        try:
            answer = await answer_direct_llm(question)
            return AskResponse(
                should_answer=True,
                mode="direct-llm",
                uncertain=False,
                answer=answer,
            )
        except Exception as e:
            return AskResponse(
                should_answer=True,
                mode="direct-llm",
                uncertain=True,
                reason=f"direct_llm_error:{type(e).__name__}",
                answer="我现在给不了稳妥结论，先稍后再试一次。",
            )

    # Route B: ziwei -> Open Notebook retrieval
    retrieval_params = build_retrieval_params(question)
    payload = {"query": question, **retrieval_params}

    try:
        result = await notebook.search(payload)
    except Exception as e:
        return AskResponse(
            should_answer=True,
            uncertain=True,
            mode="ziweidoushu-kb",
            reason=f"open_notebook_error:{type(e).__name__}",
            retrieval_params=retrieval_params,
            answer="知识库检索服务当前异常，稍后重试。",
        )

    hits = normalize_hits(result)
    strong_hits, citations = pick_evidence(hits, float(retrieval_params["minimum_score"]))

    if not strong_hits:
        return AskResponse(
            should_answer=True,
            uncertain=True,
            mode="ziweidoushu-kb",
            retrieval_params=retrieval_params,
            raw_hits=len(hits),
            citations=[],
            answer="我不确定。当前知识库证据不足，不能负责任地下结论。",
        )

    try:
        answer = await answer_ziweidoushu_with_kb(question, strong_hits, citations)
    except Exception:
        # LLM synth fallback to deterministic snippets
        snippets: list[str] = []
        for h in strong_hits[:3]:
            txt = h.get("content") or h.get("text") or h.get("snippet") or ""
            txt = str(txt).strip().replace("\n", " ")
            if txt:
                snippets.append(txt[:180])
        answer = "\n".join(f"- {s}" for s in snippets) if snippets else "证据不足。"

    return AskResponse(
        should_answer=True,
        uncertain=False,
        mode="ziweidoushu-kb",
        retrieval_params=retrieval_params,
        answer=answer,
        citations=citations,
        raw_hits=len(hits),
    )
