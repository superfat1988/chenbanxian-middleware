from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

load_dotenv()

app = FastAPI(title="Chenbanxian RAG Middleware", version="0.1.0")

FORTUNE_KEYWORDS = [
    "算命", "命理", "八字", "四柱", "大运", "流年", "桃花", "财运", "事业运", "姻缘", "合婚", "五行", "紫微", "风水", "奇门", "六爻", "卦", "运势",
]

TEACHING_KEYWORDS = ["教学", "原理", "怎么学", "解释", "入门", "讲解", "教程", "为什么"]


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


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    chat_type: Literal["private", "group"] = "private"
    addressed: bool = True
    teaching_preferred: bool = False
    force: bool = False


class AskResponse(BaseModel):
    should_answer: bool
    uncertain: bool = False
    reason: str | None = None
    mode: Literal["fortune-qa", "teaching", "reject"]
    retrieval_params: dict[str, Any] | None = None
    answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    raw_hits: int = 0


class NotebookClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OPEN_NOTEBOOK_BASE_URL", "http://192.168.2.185:5055").rstrip("/")
        self.search_path = os.getenv("OPEN_NOTEBOOK_SEARCH_PATH", "/api/search")
        self.timeout = _env_float("OPEN_NOTEBOOK_TIMEOUT_SECONDS", 25)

    async def search(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{self.search_path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r.json()


notebook = NotebookClient()


def is_fortune_intent(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in FORTUNE_KEYWORDS)


def is_teaching_intent(text: str, teaching_preferred: bool) -> bool:
    if teaching_preferred:
        return True
    t = text.lower()
    return any(k in t for k in TEACHING_KEYWORDS)


def build_retrieval_params(question: str, teaching: bool) -> dict[str, Any]:
    p = {
        "type": os.getenv("BASELINE_SEARCH_TYPE", "vector"),
        "limit": _env_int("BASELINE_LIMIT", 8),
        "minimum_score": _env_float("BASELINE_MIN_SCORE", 0.58),
        "search_sources": _env_bool("BASELINE_SEARCH_SOURCES", True),
        "search_notes": _env_bool("BASELINE_SEARCH_NOTES", False),
    }

    # 动态调参（最小）
    q = question.strip()
    if teaching:
        p["limit"] = max(int(p["limit"]), 10)
        p["minimum_score"] = min(float(p["minimum_score"]), 0.52)
    elif len(q) <= 8:
        p["limit"] = min(int(p["limit"]), 6)
        p["minimum_score"] = max(float(p["minimum_score"]), 0.62)

    return p


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


def build_answer(question: str, hits: list[dict[str, Any]], teaching: bool, min_score: float) -> tuple[bool, str, list[str]]:
    strong = [h for h in hits if hit_score(h) >= min_score]
    citations = [extract_citation(h, i + 1) for i, h in enumerate(strong[:4])]

    if not strong:
        return True, "我不确定。当前知识库证据不足，不能负责任地下结论。", []

    snippets: list[str] = []
    for h in strong[:3]:
        txt = h.get("content") or h.get("text") or h.get("snippet") or ""
        txt = str(txt).strip().replace("\n", " ")
        if txt:
            snippets.append(txt[:180])

    if teaching:
        ans = "基于现有命理资料，我先给教学式说明：\n" + "\n".join(f"- {s}" for s in snippets)
    else:
        ans = "基于检索到的命理证据，给你结论与依据：\n" + "\n".join(f"- {s}" for s in snippets)

    return False, ans, citations


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "open_notebook": notebook.base_url,
        "search_path": notebook.search_path,
    }


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    text = req.question.strip()

    # 1) 触发判定
    if not req.force:
        if req.chat_type == "group" and _env_bool("GROUP_REQUIRE_ADDRESSED", True) and not req.addressed:
            return AskResponse(should_answer=False, mode="reject", reason="group_not_addressed")

        if _env_bool("ENABLE_INTENT_GATE", True) and not is_fortune_intent(text):
            return AskResponse(
                should_answer=False,
                mode="reject",
                reason="non_fortune_intent",
                answer="我只回答命理/算命相关问题。",
            )

    # 2) 动态参数
    teaching = is_teaching_intent(text, req.teaching_preferred)
    retrieval_params = build_retrieval_params(text, teaching)

    payload = {
        "query": text,
        **retrieval_params,
    }

    # 3) 委托 Open Notebook 检索
    try:
        result = await notebook.search(payload)
    except Exception as e:
        return AskResponse(
            should_answer=True,
            uncertain=True,
            mode="fortune-qa" if not teaching else "teaching",
            reason=f"open_notebook_error: {type(e).__name__}",
            retrieval_params=retrieval_params,
            answer="我不确定。当前检索服务异常，请稍后重试。",
        )

    hits = normalize_hits(result)

    # 4) 最小拒答与输出
    uncertain, answer, citations = build_answer(
        text,
        hits,
        teaching=teaching,
        min_score=float(retrieval_params["minimum_score"]),
    )

    return AskResponse(
        should_answer=True,
        uncertain=uncertain,
        mode="teaching" if teaching else "fortune-qa",
        retrieval_params=retrieval_params,
        answer=answer,
        citations=citations,
        raw_hits=len(hits),
    )
