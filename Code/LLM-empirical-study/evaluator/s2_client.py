# -*- coding: utf-8 -*-
"""Semantic Scholar (S2) Graph API 客户端:论文检索、唯一标识获取、磁盘缓存与断点续跑。

对应 evaluation-guide.md 1.1 "S2 API 匹配:调用 API 获取 s2_id、doi、citationCount、
venue 及论文元数据"。检索结果按规范化标题缓存于 outputs/cache/s2_resolution.jsonl:
- 全部中间结果落盘,评测可中断续跑;
- 免费层共享池容易 429:内部做限速 + 指数退避(可配置),同时保存"检索失败"记录,
  供后续计算 S2 检索失败率(检索不到视为编造/失败,仅作质量参考)。

探测结论(2026-09):key 有效(伪造 key 返回 403,本 key 返回 429 限流),端点直连可达。
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

import config
from jaro_winkler import jaro_winkler
from utils import JsonlStore, log, norm_title, run_pool

API_BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = ("paperId,title,abstract,year,venue,publicationVenue,authors,"
          "citationCount,externalIds")
S2_CACHE_FILE = config.CACHE_DIR / "s2_resolution.jsonl"


class S2Client:
    """S2 检索客户端(进程内自带限速与 429 退避;检索结果缓存可跨进程复用)。"""

    def __init__(self, api_key: Optional[str] = None, cache_file: Path = S2_CACHE_FILE,
                 min_interval: Optional[float] = None, workers: int = 2):
        if min_interval is None:
            # 教程:个人 key 1 req/s;按用户要求默认 ≤10 次/分钟(6s/次)
            min_interval = config.S2_MIN_INTERVAL
        self.session = requests.Session()
        self.headers = {"x-api-key": api_key} if api_key else {}
        self.cache = JsonlStore(cache_file)
        # 请求节流(进程内全局):
        #   _min_interval 基础请求间隔,429 时放大; _cooldown_until 429 冷却结束时刻,
        #   冷却期(20s 起步,连续 429 翻倍,上限 600s)内所有线程只等待不打请求;
        #   任何 200 响应把冷却重置回初始值(表示共享池恢复)。
        self._lock = threading.Lock()
        self._base_interval = min_interval
        self._min_interval = min_interval
        self._last_ts = [0.0]
        self._cooldown = 20.0          # 当前冷却时长
        self._cooldown_until = 0.0
        self._n429 = 0                 # 统计(日志用)

    # ---------------- 基础请求(429 冷却制) ---------------- #
    def _throttle(self) -> None:
        """请求前等待:先满足冷却期,再满足最小间隔。"""
        with self._lock:
            wait = max(self._cooldown_until, self._last_ts[0] + self._min_interval) - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last_ts[0] = time.time()

    def _on_ok(self) -> None:
        """成功:共享池恢复信号,冷却与请求间隔逐步衰减回初始值。"""
        with self._lock:
            self._cooldown = 20.0
            self._min_interval = max(self._base_interval, self._min_interval / 2)

    def _on_429(self) -> float:
        """命中 429:进入短冷却(20s 起步,翻倍,上限 120s),返回需等待秒数。"""
        with self._lock:
            self._cooldown = min(self._cooldown * 2, 120.0)
            self._cooldown_until = time.time() + self._cooldown
            self._n429 += 1
            return self._cooldown

    def _get(self, path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """GET 并处理 429(冷却)/404(match 空结果)/5xx(有限重试)。

        429 说明共享配额池当前被外部用户耗尽(与自身频率无关,实测 30s 间隔仍会 429):
        进入冷却等待后重试;连续 429 超过 12 次则放弃本条(不落缓存,可下次续跑)。
        """
        backoff, max_backoff = 2.0, 60.0
        net_fails = 0                     # 网络异常上限
        misc_fails = 0                    # 非 429/4xx 状态重试上限
        n_429 = 0
        while True:
            self._throttle()
            try:
                r = self.session.get(f"{API_BASE}/{path}", params=params,
                                     headers=self.headers, timeout=30,
                                     proxies=config.PROXIES)
            except requests.RequestException as exc:
                net_fails += 1
                if net_fails >= 6:
                    raise RuntimeError(f"S2 网络持续异常: {exc}")
                log(f"S2 网络异常({path}): {exc},退避 {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
                continue
            if r.status_code == 200:
                self._on_ok()
                return r.json()
            if r.status_code == 429:
                n_429 += 1
                wait = self._on_429()
                if n_429 >= 3:            # 冷却重试 2 次仍被限流:放弃本条(不缓存,可续跑)
                    raise RuntimeError("S2 连续 429(3 次),该条放弃;请稍后重跑续传")
                log(f"S2 429(第 {n_429} 次),冷却 {wait:.0f}s")
                time.sleep(wait)          # 冷却由 _on_429 设定,此等待可被并发线程合并
                continue
            if r.status_code in (403, 401):
                raise RuntimeError(f"S2 鉴权失败({r.status_code}): 请检查 x-api-key。 {r.text[:200]}")
            if r.status_code == 404:
                # paper/match 端点对"无精确标题匹配"返回 404(而非空列表),视为正常空结果
                if path.startswith("paper/match"):
                    return {"data": []}
                raise RuntimeError(f"S2 404 异常: {r.text[:200]}")
            # 其余 5xx 等:有限次数退避后放弃(可重跑续传)
            misc_fails += 1
            if misc_fails >= 5:
                raise RuntimeError(f"S2 持续异常({r.status_code}): {r.text[:200]}")
            log(f"S2 异常状态 {r.status_code}: {r.text[:150]},退避 {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    # ---------------- 检索与解析判定 ---------------- #
    def search_candidates(self, title: str) -> List[Dict[str, Any]]:
        """两段式检索:精确 match 端点优先,search 端点兜底,返回候选(至多 6 条)。"""
        cands: List[Dict[str, Any]] = []
        try:
            hit = self._get("paper/match", {"query": title, "fields": FIELDS})
            cands += (hit or {}).get("data", []) or []
        except RuntimeError:
            raise
        if not cands:
            try:
                hit = self._get("paper/search", {"query": title, "limit": 5, "fields": FIELDS})
                cands += (hit or {}).get("data", []) or []
            except RuntimeError:
                raise
        return cands

    @staticmethod
    def _pick_best(query_title: str, cands: List[Dict[str, Any]],
                    min_sim: float) -> Dict[str, Any]:
        """按标题 JaroWinkler 相似度选最佳候选;第一作者姓氏作同分 tie-break。"""
        best: Dict[str, Any] = {"score": 0.0, "cand": None}
        for c in cands:
            sim = jaro_winkler(norm_title(query_title), norm_title(c.get("title") or ""))
            bonus = 0.0
            if best["cand"] is not None and abs(sim - best["score"]) < 1e-9:
                bonus = 0.0
            if sim > best["score"]:
                best = {"score": sim, "cand": c}
        if best["cand"] is None or best["score"] < min_sim:
            return {"status": "missing", "score": best["score"]}
        return {"status": "found", "score": best["score"], "cand": best["cand"]}

    def resolve_one(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """解析单篇论文(按条目缓存,命中直接返回)。item 需含 _key(norm title)。"""
        key = item["_key"]
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        query_title = item.get("title", "")
        rec: Dict[str, Any] = {"_key": key, "query_title": query_title,
                               "query_authors": item.get("authors", []),
                               "query_year": item.get("year")}
        # 注意:检索异常(RuntimeError)直接上抛、不入缓存 —— 下次运行会自动续跑重试
        cands = self.search_candidates(query_title)
        pick = self._pick_best(query_title, cands, config.S2_FOUND_MIN_SIM)
        if pick["status"] == "found":
            p = pick["cand"]
            authors = [a.get("name", "") for a in (p.get("authors") or [])]
            rec.update(status="found", score=round(pick["score"], 4),
                       s2_paper={
                           "paperId": p.get("paperId"),
                           "title": p.get("title"),
                           "year": p.get("year"),
                           "venue": p.get("venue") or (p.get("publicationVenue") or {}).get("name"),
                           "authors": authors,
                           "citationCount": p.get("citationCount"),
                           "doi": (p.get("externalIds") or {}).get("DOI"),
                           "abstract": p.get("abstract"),
                       })
        else:
            rec.update(status="missing", score=round(pick["score"], 4), s2_paper=None)
        return rec

    def resolve_many(self, queries: List[Dict[str, Any]], workers: int | None = None,
                     desc: str = "S2 resolve") -> Dict[str, Dict[str, Any]]:
        """批量解析(线程池 + 断点续跑),返回 key -> 记录。"""
        w = workers or 2
        # 全局限速在 S2Client 内;run_pool 间隔置 0,由客户端统一节流
        results = run_pool(queries, self._one_wrapped, self.cache,
                           workers=w, min_interval=0.0, desc=desc)
        return results

    def _one_wrapped(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return self.resolve_one(item)


# --------------------------------------------------------------------------- #
# 便捷入口
# --------------------------------------------------------------------------- #
def build_queries(works_meta: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """由 work 元数据(含 title/authors/year)构建去重后的检索条目列表。"""
    seen, out = set(), []
    for w in works_meta:
        key = norm_title(w.get("title") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"_key": key, "title": w.get("title", ""),
                    "authors": w.get("authors") or [], "year": w.get("year")})
    return out


def main() -> None:  # 自检:解析一条样例,确认网络与 key 可用
    config.ensure_dirs()
    client = S2Client(api_key=config.S2_API_KEY)
    item = {"_key": norm_title("B4: Experience with a Globally-Deployed Software Defined WAN"),
            "title": "B4: Experience with a Globally-Deployed Software Defined WAN",
            "authors": ["Sushant Jain"], "year": 2013}
    rec = client.resolve_one(item)
    print("resolve status:", rec.get("status"), "| score:", rec.get("score"))
    if rec.get("s2_paper"):
        p = rec["s2_paper"]
        print("s2Id:", p["paperId"], "| title:", p["title"], "| year:", p["year"],
              "| venue:", p["venue"], "| cites:", p["citationCount"], "| doi:", p["doi"])
        print("has abstract:", bool(p.get("abstract")))


if __name__ == "__main__":
    main()
