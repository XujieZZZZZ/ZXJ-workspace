# -*- coding: utf-8 -*-
"""通用工具:JSON 解析、jsonl 读写、线程池批量运行器(断点续跑)、文本处理。

多数组件沿用生成阶段脚本(data/LLM_extract_and_generate/*.py)中已验证的写法
(extract_json_object / load_jsonl / save_jsonl / 线程池+续跑框架),按评估需求精简重构。
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# --------------------------------------------------------------------------- #
# 日志
# --------------------------------------------------------------------------- #
def log(msg: str) -> None:
    """带时间戳的进度日志(与生成脚本风格一致)。"""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# --------------------------------------------------------------------------- #
# JSON / jsonl(模式沿用生成脚本 extract_json_object / load_jsonl / save_jsonl)
# --------------------------------------------------------------------------- #
def extract_json_object(text: str) -> Any:
    """从 LLM 回复中鲁棒地提取 JSON 对象:容忍 ```json 围栏与前后杂音。"""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        pass
    # 定位最外层 {...} 块再尝试
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(t[start:end + 1])
        except Exception:
            pass
    raise ValueError(f"无法从回复中解析 JSON。片段: {t[:200]!r}")

def load_jsonl(path: Path) -> List[dict]:
    """读 jsonl(损坏行保留原文字符串,不抛异常)。"""
    entries: List[dict] = []
    if not Path(path).exists():
        return entries
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                entries.append({"__raw__": line})
    return entries

def save_jsonl(path: Path, entries: List[dict]) -> None:
    """写 jsonl(临时文件 + os.replace 原子写)。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    tmp.replace(path)

class JsonlStore:
    """按主键去重的 jsonl 存储:供各阶段"逐条落盘、断点续跑"复用(线程安全)。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)   # 确保可写(子目录可能尚不存在)
        self._lock = threading.Lock()
        self._data: Dict[str, dict] = {}
        for e in load_jsonl(self.path):
            if "__raw__" in e:
                continue
            key = e.get("_key")
            if key:
                self._data[key] = e

    def has(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str) -> Optional[dict]:
        return self._data.get(key)

    def items(self) -> List[dict]:
        return list(self._data.values())

    def put(self, key: str, record: dict) -> None:
        record = dict(record)
        record["_key"] = key
        with self._lock:
            self._data[key] = record
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def remove(self, key: str) -> None:
        """删除指定键(如裁判失败的缓存,使下次运行可重试);整文件重写。"""
        with self._lock:
            if key not in self._data:
                return
            del self._data[key]
            tmp = self.path.with_name(self.path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                for k in sorted(self._data):
                    f.write(json.dumps(self._data[k], ensure_ascii=False) + "\n")
            tmp.replace(self.path)

# --------------------------------------------------------------------------- #
# 线程池批量运行器
# --------------------------------------------------------------------------- #
def run_pool(items: List[dict], worker: Callable[[dict], Optional[dict]],
             store: JsonlStore, workers: int = 6, min_interval: float = 0.3,
             desc: str = "task") -> Dict[str, dict]:
    """并行执行逐条任务;结果写 JsonlStore(已存在且未强制重跑则跳过)。

    worker(item) 返回要落盘的 record(通常 item 原样 + 结果字段);返回 None 表示失败。
    支持 KeyboardInterrupt 安全退出(已完成条目均已落盘,可再次运行续跑)。
    """
    todo, done = 0, 0
    pending: List[tuple] = []
    for it in items:
        key = it["_key"]
        if store.has(key):
            done += 1
            continue
        pending.append((key, it))
        todo += 1
    if not pending:
        log(f"[{desc}] 全部 {done} 条已完成,无需运行")
        return {k: store.get(k) for k in (it["_key"] for it in items)}

    _rate_lock = threading.Lock()
    _last_ts = [0.0]
    fail_keys: List[str] = []

    def _throttle() -> None:
        with _rate_lock:
            wait = _last_ts[0] + min_interval - time.time()
            if wait > 0:
                time.sleep(wait)
            _last_ts[0] = time.time()

    log(f"[{desc}] 待运行 {todo} 条(已缓存 {done} 条),workers={workers}")
    completed = 0
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for key, it in pending:
                _throttle()
                futures[pool.submit(worker, it)] = key
            for fut in as_completed(futures):
                key = futures[fut]
                try:
                    rec = fut.result()
                except Exception as exc:  # noqa: BLE001 worker 内部异常已记日志,此处兜底
                    rec = None
                    log(f"[{desc}] {key} 异常: {exc}")
                if rec is not None:
                    store.put(key, rec)
                else:
                    fail_keys.append(key)
                completed += 1
                if completed % 10 == 0 or completed == todo:
                    log(f"[{desc}] 进度 {completed}/{todo} 成功 {todo - len(fail_keys) - (todo - completed)}")
    except KeyboardInterrupt:
        log(f"[{desc}] 收到中断,已完成的 {completed} 条均已落盘,可重跑续传")
        raise
    if fail_keys:
        log(f"[{desc}] 完成: {completed - len(fail_keys)} 成功, {len(fail_keys)} 失败(keys: {fail_keys[:10]})")
    return {k: store.get(k) for k in (it["_key"] for it in items)}

# --------------------------------------------------------------------------- #
# 文本处理
# --------------------------------------------------------------------------- #
_PUNCT_RE = re.compile(r"[\W_]+", re.UNICODE)  # \W 去除非字母数字与下划线

def norm_title(title: str) -> str:
    """规范化论文标题:小写、仅保留字母数字、折叠空白 -> 用于集合去重与缓存键。

    注:匹配判定(Level-2 JaroWinkler)用的是原始标题,规范化只服务于去重/寻址。
    """
    t = _PUNCT_RE.sub(" ", (title or "").lower())
    return " ".join(t.split())

def text_hash(text: str, length: int = 16) -> str:
    """文本 sha1 前缀,作嵌入/检索缓存键。"""
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:length]

def truncate_chars(text: str, limit: int) -> str:
    """按字符截断(近似截断即可,编码层另有 token 级截断)。"""
    text = text or ""
    return text[:limit] if len(text) > limit else text

def clean_json_number(v: Any, lo: int, hi: int, default: int) -> int:
    """把 LLM 输出的数值字段收敛为 [lo,hi] 内的整数(裁判打分健壮性)。"""
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))
