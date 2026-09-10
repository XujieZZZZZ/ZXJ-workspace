# -*- coding: utf-8 -*-
"""RQ2-3 评测入口:python run_rq2_3.py [--limit N] [--redo] [--backend qwen|deepseek|glm] [--workers M]

对 withsearch / withoutsearch 两个变体分别:
  1) 成对双盲判定(位置对调 ×2/样本,主裁判) -> 偏好冲突判 Tie;
  2) 交叉裁判稳定性:同一批成对任务用第二个后端(默认 DeepSeek)再评一轮,
     比较两裁判的胜率与逐样本一致性(默认开启;--no-cross 关闭);
  3) identical-pair 控制实验(默认开启;--no-sanity 关闭):把同一方案放在 A/B 两侧
     提交裁判,理想输出应为 Tie —— 用于暴露位置偏置/判定噪声;
  4) 独立 Rubric 交叉验证(LLM-RW Sol 单独打分;Human-RW Sol 复用 RQ2-2 结果);
  5) 归因:调用 RQ2-1 报告中的文档级指标(recall / Rel / 幻觉率=1-P)
     与 Δ 做 Spearman 相关(3 条假设)。

缓存按 (任务, 后端) 分流存储:不同裁判互不覆盖,已缓存条目自动跳过 -> 幂等补跑。
归因需要先跑完 RQ2-1(报告 outputs/reports/rq2_1_{variant}.json)。
报告:outputs/reports/rq2_3_{variant}.md / .json。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Optional

import config
import dataio
import rq2_3 as r23
from judge import JudgeLLM, JsonlStore, log, run_judge_tasks
from report import banner, fmt, md_section, md_table, pct, write_json, write_text

JUDGE_SUBDIR = config.JUDGE_DIR / "rq2_3"
RUBRIC_STORE_RQ22 = config.JUDGE_DIR / "rq2_2" / "rubric.jsonl"
CROSS_BACKEND_DEFAULT = "deepseek"     # 与主裁判交叉的第二后端


def _store(kind: str) -> JsonlStore:
    return JsonlStore(JUDGE_SUBDIR / f"{kind}.jsonl")


def _backend_store(kind: str, backend: str) -> JsonlStore:
    """裁判相关缓存文件:qwen 保持旧文件名(兼容历史缓存),其他后端带后缀。"""
    if backend == "qwen":
        return JsonlStore(JUDGE_SUBDIR / f"{kind}.jsonl")
    return JsonlStore(JUDGE_SUBDIR / f"{kind}_{backend}.jsonl")


def load_rq2_1_metrics(variant: str) -> Dict[str, dict]:
    """读取 RQ2-1 文档级结果(归因自变量),缺失则报错提示先跑 RQ2-1。"""
    p = config.REPORTS_DIR / f"rq2_1_{variant}.json"
    if not p.exists():
        raise FileNotFoundError(f"缺少 {p},请先运行 run_rq2_1.py(归因需要 RQ2-1 指标)")
    data = json.loads(p.read_text(encoding="utf-8"))
    return {r["pdf_id"]: r for r in data["per_sample"]}


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="RQ2-3 Solution 对比与归因评估")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--backend", default=None,
                    choices=["qwen", "deepseek", "glm"], help="主裁判后端(默认 qwen)")
    ap.add_argument("--cross-backend", default=None,
                    help="交叉裁判后端(默认 deepseek;主裁判为 deepseek 时交叉为 qwen)")
    ap.add_argument("--no-cross", action="store_true", help="关闭交叉裁判稳定性检查")
    ap.add_argument("--no-sanity", action="store_true", help="关闭 identical-pair 控制实验")
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()

    config.ensure_dirs()
    t0 = time.time()
    main_backend = args.backend or config.LLM_BACKEND or "qwen"
    if args.cross_backend:
        cross_backend = args.cross_backend
    elif main_backend == CROSS_BACKEND_DEFAULT:
        cross_backend = "qwen"
    else:
        cross_backend = CROSS_BACKEND_DEFAULT
    judge_main = JudgeLLM(backend=main_backend)
    judges_cross = JudgeLLM(backend=cross_backend) if not args.no_cross else None
    pdfs = dataio.list_pdf_ids()
    if args.limit:
        pdfs = pdfs[:args.limit]
    log(f"RQ2-3 开始:主裁判={main_backend} 交叉裁判={cross_backend if judges_cross else '无(关闭)'}")

    for variant in dataio.RW_VARIANTS:
        log(f"=== 变体 {variant} ===")
        # 1) 成对双盲判定(主裁判)
        pair_items = _pair_items(pdfs, variant)
        run_judge_tasks(pair_items, "pairwise", judge_main,
                        _backend_store(f"pair_{variant}", main_backend),
                        redo=args.redo, workers=args.workers, desc=f"pair:{variant}:{main_backend}")
        # 2) 交叉裁判(默认 DeepSeek):同一批任务再评一轮 -> 胜率稳定性
        if judges_cross is not None:
            run_judge_tasks(pair_items, "pairwise", judges_cross,
                            _backend_store(f"pair_{variant}", cross_backend),
                            redo=args.redo, workers=args.workers,
                            desc=f"pair:{variant}:{cross_backend}")
        # 3) identical-pair 控制实验:同方案在 A/B 两侧,裁判应判 Tie
        if not args.no_sanity:
            for backend, judge in ((main_backend, judge_main),
                                   (cross_backend, judges_cross) if judges_cross else ()):
                _run_sanity(pdfs, variant, backend, judge, redo=args.redo,
                            workers=args.workers)
        # 4) 独立 Rubric(主裁判;LLM-RW Sol 打分)
        rub_items: List[dict] = []
        for pid in pdfs:
            doc_gt = dataio.load_doc(dataio.SET_GT, pid)
            doc_llm = dataio.load_doc(variant, pid)
            rub_items.append({"_key": f"{pid}|{variant}|rubric",
                              "obs": doc_gt["observation"],
                              "rw_text": _render_rw(doc_llm),
                              "sol_text": _sol_text(doc_llm)})
        run_judge_tasks(rub_items, "rubric_score", judge_main,
                        _backend_store(f"rubric_{variant}", main_backend),
                        redo=args.redo, workers=args.workers,
                        desc=f"rubric:{variant}:{main_backend}")
        # 5) 汇总
        per_sample = _assemble(pdfs, variant, main_backend, cross_backend)
        # 6) 归因(需 RQ2-1 结果)
        try:
            rq21 = load_rq2_1_metrics(variant)
            attribution = _attribution(pdfs, variant, rq21, main_backend)
        except FileNotFoundError as exc:
            log(f"跳过归因: {exc}")
            attribution = None
        _write_report(variant, per_sample, attribution,
                      main_backend, cross_backend)
        _console(variant, per_sample, attribution, main_backend, cross_backend)
    usage = f"主({main_backend})={judge_main.usage()}"
    if judges_cross is not None:
        usage += f" 交叉({cross_backend})={judges_cross.usage()}"
    log(f"RQ2-3 完成,耗时 {time.time() - t0:.0f}s,LLM usage: {usage}")


def _pair_items(pdfs: List[str], variant: str) -> List[dict]:
    items = []
    for pid in pdfs:
        doc_llm = dataio.load_doc(variant, pid)
        doc_hrw = dataio.load_doc(dataio.SET_HUMAN_RW, pid)
        items += r23.pairwise_items(pid, variant, doc_llm, doc_hrw)
    return items


def _run_sanity(pdfs: List[str], variant: str, backend: str, judge: JudgeLLM,
                redo: bool, workers: Optional[int]) -> None:
    """identical-pair 控制:同方案 A==B,swap 两轮由 run 外的两个顺序任务执行。"""
    items = []
    for pid in pdfs:
        doc_llm = dataio.load_doc(variant, pid)
        sol = _sol_text(doc_llm)
        obs = doc_llm.get("observation") or ""
        items.append({"_key": f"{pid}|{variant}|sanity", "obs": obs,
                      "sol_a": sol, "sol_b": sol,
                      "label_a": "A", "label_b": "B",
                      "_identical": True,           # 标记 identical 控制(validator 宽容)
                      "variant": variant, "pdf_id": pid})
    run_judge_tasks(items, "pairwise", judge,
                    _backend_store(f"sanity_{variant}", backend),
                    redo=redo, workers=workers, desc=f"sanity:{variant}:{backend}")


def _sanity_tie_rate(pdf_ids: List[str], variant: str, backend: str) -> dict:
    """统计 identical-pair 的 Tie 率与偏置样本(理想应全 Tie)。"""
    store = _backend_store(f"sanity_{variant}", backend)
    ties = non_tie = 0
    details = []
    for pid in pdf_ids:
        rec = store.get(f"{pid}|{variant}|sanity")
        if not rec or not rec.get("ok"):
            details.append({"pdf_id": pid, "preference": None})
            continue
        pref = rec["result"]["preference"]
        if pref == "Tie":
            ties += 1
        else:
            non_tie += 1
        details.append({"pdf_id": pid, "preference": pref})
    n = ties + non_tie
    return {"backend": backend, "tie_rate": ties / n if n else None,
            "n": n, "details": details}


# --------------------------------------------------------------------------- #
def _render_rw(doc: dict) -> str:
    lines = []
    for block in doc.get("related_works") or []:
        for c in block.get("claims") or []:
            lines.append(f"[Claim] {c}")
        for w in block.get("works") or []:
            auth = (w.get("authors") or [""])[0]
            lines.append(f"  - {w.get('title', '')} ({auth}, {w.get('year') or 'n/a'})")
    return "\n".join(lines)


def _sol_text(doc: dict) -> str:
    sol = doc.get("solution") or {}
    return f"[Idea]\n{sol.get('idea', '')}\n\n[Implementation]\n{sol.get('implementation', '')}"[:16000]


def _outcome_of(pair_store: JsonlStore, pid: str, variant: str) -> Optional[str]:
    o1 = pair_store.get(f"{pid}|{variant}|pair|o1")
    o2 = pair_store.get(f"{pid}|{variant}|pair|o2")
    if o1 and o1.get("ok") and o2 and o2.get("ok"):
        return r23.resolve_outcome(o1, o2)
    return None


def _assemble(pdfs: List[str], variant: str, main_backend: str,
              cross_backend: str) -> List[dict]:
    """每样本:主/交叉裁判的成对结果、identical-pair 控制、Rubric 交叉验证分。"""
    pair_main = _backend_store(f"pair_{variant}", main_backend)
    pair_cross = _backend_store(f"pair_{variant}", cross_backend)
    rub_store = _backend_store(f"rubric_{variant}", main_backend)
    rub_human = JsonlStore(RUBRIC_STORE_RQ22)
    out = []
    for pid in pdfs:
        o1 = pair_main.get(f"{pid}|{variant}|pair|o1")
        o2 = pair_main.get(f"{pid}|{variant}|pair|o2")
        rec = {"pdf_id": pid}
        if o1 and o1.get("ok") and o2 and o2.get("ok"):
            rec["pref_o1"] = o1["result"]["preference"]
            rec["pref_o2"] = o2["result"]["preference"]
            rec["outcome"] = r23.resolve_outcome(o1, o2)
            rec["scores_pair"] = r23.scores_from_pairwise(o1, o2)
            rec["delta_pair"] = r23.delta_from_pairwise(o1, o2)
        else:
            rec["outcome"] = None
        # 交叉裁判结果(胜率稳定性)
        oc = _outcome_of(pair_cross, pid, variant)
        rec["cross_outcome"] = oc
        rec["cross_backend"] = cross_backend if oc is not None else None
        # 独立 rubric 交叉验证(主裁判,带 RW 上下文)
        r_llm = rub_store.get(f"{pid}|{variant}|rubric")
        r_hrw = rub_human.get(f"{pid}|human_re|rubric")
        rec["rubric_llm"] = {k: r_llm["result"][k] for k in
                             ("targetedness", "feasibility", "novelty", "groundedness")} \
            if r_llm and r_llm.get("ok") else None
        rec["rubric_hrw"] = {k: r_hrw["result"][k] for k in
                             ("targetedness", "feasibility", "novelty", "groundedness")} \
            if r_hrw and r_hrw.get("ok") else None
        if rec["rubric_llm"] and rec["rubric_hrw"]:
            rec["delta_rubric"] = {k: rec["rubric_llm"][k] - rec["rubric_hrw"][k]
                                   for k in rec["rubric_llm"]}
        out.append(rec)
    return out


def _attribution(pdfs: List[str], variant: str, rq21: Dict[str, dict],
                 main_backend: str) -> dict:
    """三假设的 Spearman 相关:X=R/Rel/幻觉率 vs Y=Δ(grd/tgt/feas)。"""
    rows = []
    for pid in pdfs:
        rec = rq21.get(pid)
        if not rec:
            continue
        rows.append({"pdf_id": pid,
                     "recall": rec["retrieval"]["recall"],
                     "precision": rec["retrieval"]["precision"],
                     "rel": rec["semantic"]["rel_l"],
                     "halluc": 1.0 - rec["retrieval"]["precision"]})
    pair_store = _backend_store(f"pair_{variant}", main_backend)
    deltas = {}
    for pid in pdfs:
        o1 = pair_store.get(f"{pid}|{variant}|pair|o1")
        o2 = pair_store.get(f"{pid}|{variant}|pair|o2")
        if o1 and o1.get("ok") and o2 and o2.get("ok"):
            deltas[pid] = r23.delta_from_pairwise(o1, o2)
    out = []
    for hyp in r23.HYPOTHESES:
        ys = [deltas[r["pdf_id"]][hyp["y"]] for r in rows if r["pdf_id"] in deltas]
        xs = [r[hyp["x"]] for r in rows if r["pdf_id"] in deltas]
        corr = r23.spearman(xs, ys)
        out.append({"hypothesis": hyp["name"], "x": hyp["x"], "y": hyp["y"],
                    "expect": hyp["expect"], "spearman": corr})
    return {"items": out, "n_x": len(rows), "n_delta": len(deltas)}


# --------------------------------------------------------------------------- #
def _write_report(variant: str, per_sample: List[dict],
                  attribution: Optional[dict], main_backend: str,
                  cross_backend: str) -> None:
    has_cross = any(r.get("cross_outcome") is not None for r in per_sample)
    out = [f"# RQ2-3 评估报告:LLM-RW vs Human-RW 对 Solution 的影响(变体: {variant})\n",
           f"- 样本数: {len(per_sample)};双盲成对判定:位置对调两次,冲突判 Tie\n"
           f"- 主裁判后端: {main_backend};交叉裁判(胜率稳定性): "
           f"{cross_backend if has_cross else '未启用'};\n"
           f"- identical-pair 控制实验默认开启(同方案 A==B,理想输出为 Tie)\n"]
    # 3.1 成对结果(主裁判)
    rows, wins = [], {"Win_LLM": 0, "Win_Human": 0, "Tie": 0}
    for r in per_sample:
        outcm = r.get("outcome")
        if outcm:
            wins[outcm] += 1
        rows.append([r["pdf_id"], r.get("pref_o1", "-"), r.get("pref_o2", "-"),
                     outcm or "-",
                     fmt((r.get("scores_pair") or {}).get("llm", {}).get("total", None)),
                     fmt((r.get("scores_pair") or {}).get("human", {}).get("total", None)),
                     fmt((r.get("delta_pair") or {}).get("total", None))])
    n = max(sum(wins.values()), 1)
    # 3.1 均值行(全部 N 样本的连续分数/差值;与偏好判定无关)
    valid = [r for r in per_sample if (r.get("scores_pair") or {}).get("llm")]

    def _mean_of(getter):
        vals = [getter(r) for r in valid]
        vals = [v for v in vals if v is not None]
        return (sum(vals) / len(vals)) if vals else None

    mean_llm = _mean_of(lambda r: (r["scores_pair"]["llm"].get("total")))
    mean_hrw = _mean_of(lambda r: (r["scores_pair"]["human"].get("total")))
    mean_dlt = _mean_of(lambda r: (r.get("delta_pair") or {}).get("total"))
    rows.append(["mean(全部样本)", "-", "-", "-",
                 fmt(mean_llm), fmt(mean_hrw), fmt(mean_dlt)])
    sec3_1 = (md_table(["样本", "O1 偏好", "O2 偏好", "有效判定",
                        "Sol_LLM 总分", "Sol_HumanRW 总分", "Δ total"], rows)
              + "\n\n**胜率统计**\n\n"
              + md_table(["指标", "值"],
                         [["WinRate_LLM_RW", pct(wins["Win_LLM"] / n)],
                          ["WinRate_Human_RW", pct(wins["Win_Human"] / n)],
                          ["Tie 率", pct(wins["Tie"] / n)],
                          ["有效样本 N", n]])
              + "\n\n注:O1/O2 列为裁判输出的原始偏好标签(A/B/Tie);两轮任务中"
                "标签与内容绑定一致(A=Sol_LLM_RW、B=Sol_Human_RW),仅交换展示顺序"
                "(O1 先展示 Sol_LLM_RW、O2 先展示 Sol_Human_RW)。"
                "两轮偏好指向不同内容(即位置冲突)时,按指南有效判定为 Tie。")
    out.append(md_section(f"3.1 成对双盲对比(位置对调;裁判={main_backend})", sec3_1))
    # 3.1b Δ 四维
    dims = ["targetedness", "feasibility", "novelty", "groundedness"]
    d_rows = []
    for r in per_sample:
        d = (r.get("delta_pair") or {})
        d_rows.append([r["pdf_id"]] + [fmt(d.get(k)) for k in dims] + [fmt(d.get("total"))])
    # Δ 均值行(全部样本)
    d_mean = {k: _mean_of(lambda r, k=k: (r.get("delta_pair") or {}).get(k)) for k in dims}
    d_rows.append(["mean(全部样本)"] + [fmt(d_mean[k]) for k in dims]
                  + [fmt(_mean_of(lambda r: (r.get("delta_pair") or {}).get("total")))])
    out.append(md_section(f"方案得分差值 Δ_i^k = Score_k(Sol_LLM_RW) - Score_k(Sol_Human_RW)"
                          f"(成对两轮均值;裁判={main_backend})",
                          md_table(["样本"] + dims + ["Δ total"], d_rows)))
    # 3.1d 交叉裁判稳定性(胜率稳定性)
    if has_cross:
        xrows, wins_x = [], {"Win_LLM": 0, "Win_Human": 0, "Tie": 0, None: 0}
        agree = 0
        for r in per_sample:
            oc = r.get("cross_outcome")
            if oc:
                wins_x[oc] += 1
            xrows.append([r["pdf_id"], r.get("outcome") or "-", oc or "-",
                          "一致" if r.get("outcome") == oc else "分歧"])
            if r.get("outcome") == oc:
                agree += 1
        nx = max(sum(wins_x.values()), 1)
        out.append(md_section(
            f"3.1d 交叉裁判胜率稳定性(主={main_backend} vs 交叉={cross_backend},同一批双盲成对任务)",
            md_table(["样本", f"判定({main_backend})", f"判定({cross_backend})", "一致?"], xrows)
            + "\n\n**胜率对比**\n\n" + md_table(
                ["指标", f"{main_backend}", f"{cross_backend}"],
                [["WinRate_LLM_RW", pct(wins["Win_LLM"] / n),
                  pct(wins_x["Win_LLM"] / nx)],
                 ["WinRate_Human_RW", pct(wins["Win_Human"] / n),
                  pct(wins_x["Win_Human"] / nx)],
                 ["Tie 率", pct(wins["Tie"] / n), pct(wins_x["Tie"] / nx)],
                 ["样本一致率", "-", pct(agree / max(len(per_sample), 1))]])))
    # 3.1e identical-pair 控制实验
    sanity_rows = []
    for backend in ((main_backend, cross_backend) if has_cross else (main_backend,)):
        st = _sanity_tie_rate([r["pdf_id"] for r in per_sample], variant, backend)
        if st["n"]:
            details = "、".join(f"{d['pdf_id']}:{d['preference']}" for d in st["details"]
                                if d["preference"] != "Tie") or "(全部 Tie)"
            sanity_rows.append([backend, pct(st["tie_rate"]), st["n"], details])
    if sanity_rows:
        out.append(md_section("3.1e identical-pair 控制实验(同方案 A==B;理想输出应全部 Tie)",
                              md_table(["裁判", "Tie 率", "N", "非 Tie 样本"],
                                       sanity_rows)
                              + "\n\n解读:Tie 率高说明位置偏置/判定噪声小;若某裁判大量非 Tie,"
                                "其成对胜率需谨慎解读。"))
    # 3.1c rubric 交叉验证(主裁判,非盲,带 RW 上下文)
    c_rows = []
    for r in per_sample:
        rl, rh = r.get("rubric_llm"), r.get("rubric_hrw")
        if rl and rh:
            c_rows.append([r["pdf_id"]] +
                          [f"{rl[k]}(LLM) / {rh[k]}(Human)" for k in dims])
    if c_rows:
        c_llm = {k: _mean_of(lambda r, k=k: (r.get("rubric_llm") or {}).get(k)) for k in dims}
        c_hrw = {k: _mean_of(lambda r, k=k: (r.get("rubric_hrw") or {}).get(k)) for k in dims}
        c_rows.append(["mean(全部样本)"] +
                      [f"{fmt(c_llm[k], 2)}(LLM) / {fmt(c_hrw[k], 2)}(Human)" for k in dims])
        out.append(md_section(f"3.1c 独立 Rubric 交叉验证(带 RW 上下文,非盲;裁判={main_backend})",
                              md_table(["样本"] + dims, c_rows)))
    # 3.2 归因
    if attribution:
        a_rows = []
        for it in attribution["items"]:
            s = it.get("spearman")
            a_rows.append([it["hypothesis"], it["x"] + " -> " + it["y"],
                           it["expect"],
                           fmt(s["rho"]) if s else "-",
                           fmt(s["p"], 3) if s else "-",
                           s["n"] if s else "-"])
        out.append(md_section("3.2 归因:Spearman 相关(N=样本数,小样本解释力有限,仅作趋势参考)",
                              md_table(["假设", "X -> Y", "预期", "ρ", "p", "n"], a_rows)
                              + f"\n\n样本数: X={attribution['n_x']}, Δ={attribution['n_delta']}"))
    else:
        out.append(md_section("3.2 归因分析", "跳过(缺少 RQ2-1 结果,请先运行 run_rq2_1.py)"))
    write_text(config.REPORTS_DIR / f"rq2_3_{variant}.md", "\n".join(out))
    write_json(config.REPORTS_DIR / f"rq2_3_{variant}.json",
               {"variant": variant, "main_backend": main_backend,
                "cross_backend": cross_backend,
                "per_sample": per_sample, "attribution": attribution})


def _console(variant: str, per_sample: List[dict], attribution: Optional[dict],
             main_backend: str, cross_backend: str) -> None:
    print(banner(f"RQ2-3 摘要 [变体: {variant}](完整报告: outputs/reports/rq2_3_{variant}.md)"))
    wins = {"Win_LLM": 0, "Win_Human": 0, "Tie": 0}
    wins_x = {"Win_LLM": 0, "Win_Human": 0, "Tie": 0}
    for r in per_sample:
        o = r.get("outcome")
        if o:
            wins[o] += 1
        oc = r.get("cross_outcome")
        if oc:
            wins_x[oc] += 1
        d = (r.get("delta_pair") or {})
        cross = f" | 交叉判定={oc or '-'}" if oc is not None else ""
        print(f"  {r['pdf_id']} | {str(o):9s}{cross} | Δ(tgt {fmt(d.get('targetedness'))}, "
              f"feas {fmt(d.get('feasibility'))}, nov {fmt(d.get('novelty'))}, "
              f"grd {fmt(d.get('groundedness'))})")
    n = max(sum(wins.values()), 1)
    print(f"-- [{main_backend}] WinRate_LLM_RW={pct(wins['Win_LLM'] / n)} "
          f"WinRate_Human_RW={pct(wins['Win_Human'] / n)} Tie={pct(wins['Tie'] / n)} (N={n})")
    if wins_x and sum(wins_x.values()):
        nx = sum(wins_x.values())
        print(f"-- [{cross_backend}] WinRate_LLM_RW={pct(wins_x['Win_LLM'] / nx)} "
              f"WinRate_Human_RW={pct(wins_x['Win_Human'] / nx)} Tie={pct(wins_x['Tie'] / nx)} (N={nx})")
    # identical-pair 控制
    for backend in ((main_backend, cross_backend) if wins_x and sum(wins_x.values())
                    else (main_backend,)):
        st = _sanity_tie_rate([r["pdf_id"] for r in per_sample], variant, backend)
        if st["n"]:
            print(f"-- [identical-pair/{backend}] Tie 率={pct(st['tie_rate'])} (N={st['n']})")
    if attribution:
        for it in attribution["items"]:
            s = it.get("spearman")
            print(f"-- {it['hypothesis']}: ρ={fmt(s['rho']) if s else '-'} "
                  f"(p={fmt(s['p'], 3) if s else '-'}, n={s['n'] if s else '-'})")


if __name__ == "__main__":
    sys.exit(main())
