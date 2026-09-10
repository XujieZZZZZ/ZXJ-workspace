# -*- coding: utf-8 -*-
"""RQ2-2 评测入口:python run_rq2_2.py [--limit N] [--redo] [--backend qwen|glm] [--workers M]

数据:输入=Observation + Human RW(S_H),输出=LLM Solution(Sol_L,即 merged_human_re 的 solution);
GT=人类 Solution(Sol_H,human_data)。
流程:4 维 Rubric 裁判打分(RQ2-1 runner 无此项;此处独立跑) + SPECTER2 语义相似度
      + Human Sol 关键技术要素抽取 -> Sol_L 覆盖判定(AspectRecall)。
报告:outputs/reports/rq2_2.md / rq2_2.json。
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import List, Optional

import config
import dataio
import rq2_2 as r22
from embedder import Specter2Embedder
from judge import JudgeLLM, JsonlStore, run_judge_tasks
from report import banner, fmt, md_section, md_table, pct, write_json, write_text
from utils import log

JUDGE_SUBDIR = config.JUDGE_DIR / "rq2_2"


def _store(kind: str) -> JsonlStore:
    return JsonlStore(JUDGE_SUBDIR / f"{kind}.jsonl")


def main() -> None:
    ap = argparse.ArgumentParser(description="RQ2-2 Solution 质量评估")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--redo", action="store_true", help="重跑 LLM 裁判")
    ap.add_argument("--backend", default=None, choices=["qwen", "deepseek", "glm"])
    ap.add_argument("--emb", default=config.EMB_DEFAULT, choices=list(config.EMB_CHOICES),
                    help="语义编码器(specter2_base 保持既有结果;specter2/scibert 输出到新文件)")
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()

    config.ensure_dirs()
    t0 = time.time()
    judge = JudgeLLM(backend=args.backend)
    _spec = config.EMB_CHOICES[args.emb]
    emb = Specter2Embedder(model_dir=_spec[0],
                           name=None if args.emb == config.EMB_DEFAULT else args.emb,
                           adapter_dir=_spec[2], pooling=_spec[3])
    log(f"RQ2-2 语义编码器: {args.emb} = {config.EMB_CHOICES[args.emb][1]}")

    pdfs = dataio.list_pdf_ids()
    if args.limit:
        pdfs = pdfs[:args.limit]

    # 1) Rubric 打分:
    #    a) Sol_L(LLM solution,输入 Human RW)——主评估对象;
    #    b) Sol_H(人类 solution 基线)——同上下文(obs + Human RW)同量表打分,作为对照。
    rub_items, rub_human_items, rows = [], [], []
    for pid in pdfs:
        doc_gt = dataio.load_doc(dataio.SET_GT, pid)          # 人类 GT(Sol_H / S_H)
        doc_sol = dataio.load_doc(dataio.SET_HUMAN_RW, pid)   # LLM solution(输入 Human RW)
        rows.append({"pdf_id": pid, "doc_gt": doc_gt, "doc_sol": doc_sol})
        rub_items += r22.rubric_items(pid, dataio.SET_HUMAN_RW, doc_gt, doc_sol)
        # 人类基线:评 Sol_H(原文抽取的论文 solution)
        rub_human_items.append({"_key": f"{pid}|human_sol|rubric",
                                "obs": doc_gt["observation"],
                                "rw_text": r22.render_rw_for_judge(doc_sol),
                                "sol_text": r22.sol_text_of(doc_gt)})
    log(f"RQ2-2 Rubric 打分任务: {len(rub_items)} 条(LLM Sol)+ {len(rub_human_items)} 条(Human Sol 基线)")
    # 两组任务合并为一次批量提交(同一 store;拆分提交会使 --redo 后一次清掉前一次结果)
    all_rub_items = rub_items + rub_human_items
    run_judge_tasks(all_rub_items, "rubric_score", judge, _store("rubric"),
                    redo=args.redo, workers=args.workers, desc="rubric")

    # 2) 关键技术要素:抽取(蓝本=Sol_H)+ 覆盖判定(对象=Sol_L)
    ext_items, cov_items = [], []
    for pid in pdfs:
        doc_gt = dataio.load_doc(dataio.SET_GT, pid)
        doc_sol = dataio.load_doc(dataio.SET_HUMAN_RW, pid)
        ext_items += r22.aspect_items(pid, doc_gt, doc_sol)[:1]
        cov_items += r22.aspect_items(pid, doc_gt, doc_sol)[1:]
    log(f"Aspect 抽取任务: {len(ext_items)} 条")
    run_judge_tasks(ext_items, "aspect_extract", judge, _store("aspect_extract"),
                    redo=args.redo, workers=args.workers, desc="aspect-extract")
    for it in cov_items:   # 回填抽取结果 -> 组装覆盖判定
        dec = _store("aspect_extract").get(it["_key"].replace("aspect_coverage", "aspect_extract"))
        it["aspects"] = (dec or {}).get("result", {}).get("aspects", []) if dec and dec.get("ok") else []
    run_judge_tasks(cov_items, "aspect_coverage", judge, _store("aspect_coverage"),
                    redo=args.redo, workers=args.workers, desc="aspect-coverage")

    # 3) 汇总每样本结果
    per_sample = []
    for pid in pdfs:
        rec = _assemble(pid, emb)
        per_sample.append(rec)
    _write_report(per_sample, args.emb)
    _console(per_sample)
    log(f"RQ2-2 完成,耗时 {time.time() - t0:.0f}s,LLM usage: {judge.usage()}")


def _assemble(pid: str, emb: Specter2Embedder) -> dict:
    doc_gt = dataio.load_doc(dataio.SET_GT, pid)
    doc_sol = dataio.load_doc(dataio.SET_HUMAN_RW, pid)
    rec = {"pdf_id": pid}
    rub = _store("rubric").get(f"{pid}|human_re|rubric")
    if rub and rub.get("ok"):
        scores = {k: rub["result"][k] for k in ("targetedness", "feasibility",
                                                "novelty", "groundedness")}
        rec["rubric"] = {**scores, "weighted_total": r22.weighted_total(scores),
                         "reason": rub["result"].get("reason", "")[:200]}
    else:
        rec["rubric"] = None
    # 人类 Solution 基线(同上下文评分)
    rub_h = _store("rubric").get(f"{pid}|human_sol|rubric")
    if rub_h and rub_h.get("ok"):
        scores_h = {k: rub_h["result"][k] for k in ("targetedness", "feasibility",
                                                    "novelty", "groundedness")}
        rec["rubric_human"] = {**scores_h, "weighted_total": r22.weighted_total(scores_h)}
    else:
        rec["rubric_human"] = None
    rec["semantic_sim"] = r22.semantic_similarity(doc_gt, doc_sol, emb)
    ext = _store("aspect_extract").get(f"{pid}|aspect_extract")
    aspects = (ext or {}).get("result", {}).get("aspects", []) if ext and ext.get("ok") else []
    cov = _store("aspect_coverage").get(f"{pid}|aspect_coverage")
    coverage = (cov or {}).get("result", {}).get("coverage", []) if cov and cov.get("ok") else []
    rec["aspects"] = aspects
    rec["aspect_recall"] = r22.aspect_recall(coverage, len(aspects))
    rec["aspect_covered"] = sum(1 for c in coverage if c.get("addressed") == 1)
    return rec


def _mean(per_sample: List[dict]) -> dict:
    rubs = [r["rubric"] for r in per_sample if r["rubric"]]
    out = {"n": len(rubs)}
    for k in ("targetedness", "feasibility", "novelty", "groundedness"):
        out[k] = sum(rub[k] for rub in rubs) / len(rubs) if rubs else None
    out["weighted_total"] = sum(rub["weighted_total"] for rub in rubs) / len(rubs) if rubs else None
    # 人类 Sol 基线聚合
    hrubs = [r["rubric_human"] for r in per_sample if r["rubric_human"]]
    out["human"] = {}
    for k in ("targetedness", "feasibility", "novelty", "groundedness"):
        out["human"][k] = sum(h[k] for h in hrubs) / len(hrubs) if hrubs else None
    out["human"]["weighted_total"] = sum(h["weighted_total"] for h in hrubs) / len(hrubs) \
        if hrubs else None
    sims = [r["semantic_sim"] for r in per_sample]
    out["semantic_sim"] = sum(sims) / len(sims) if sims else None
    n_cov = sum(r["aspect_covered"] for r in per_sample)
    n_aspect = sum(len(r["aspects"]) for r in per_sample)
    out["aspect_recall"] = n_cov / n_aspect if n_aspect else None
    out["aspect_covered"] = n_cov
    out["aspect_total"] = n_aspect
    return out


def _write_report(per_sample: List[dict], emb_name: str = config.EMB_DEFAULT) -> None:
    tag = "" if emb_name == config.EMB_DEFAULT else f"_emb_{emb_name}"
    m = _mean(per_sample)
    out = ["# RQ2-2 评估报告:基于人类 Related Work 的 Solution 生成能力\n",
           f"- 样本数: {len(per_sample)}(Observation + S_H -> Sol_L;GT=Sol_H)\n"
           f"- 语义编码器: {config.EMB_CHOICES[emb_name][1]}(--emb {emb_name});"
           "向量缓存与输出按编码器隔离,不覆盖其他编码器的结果\n"
           "- 加权总分:均权 w=0.25(见 config.SOL_WEIGHTS);四维 1-5 分\n"]
    rows = []
    for r in per_sample:
        rub = r["rubric"]
        if rub:
            rows.append([r["pdf_id"], rub["targetedness"], rub["feasibility"],
                         rub["novelty"], rub["groundedness"],
                         fmt(rub["weighted_total"], 2), fmt(r["semantic_sim"], 3),
                         f"{r['aspect_covered']}/{len(r['aspects'])}", pct(r["aspect_recall"])])
    out.append(md_section("2.1-2.2 四维 Rubric / 语义相似度 / 技术要素覆盖率",
                          md_table(["样本", "s_tgt", "s_feas", "s_nov", "s_grd",
                                    "加权总分", "语义相似(cos)", "覆盖 K", "AspectRecall"], rows)))
    # 人类 Solution 基线对比(同上下文同量表)
    hrows = []
    for r in per_sample:
        h = r.get("rubric_human")
        if h:
            hrows.append([r["pdf_id"], h["targetedness"], h["feasibility"], h["novelty"],
                          h["groundedness"], fmt(h["weighted_total"], 2)])
    if hrows:
        out.append(md_section("2.1b 人类 Solution 基线(同上下文 rubric;对照用)",
                              md_table(["样本", "s_tgt", "s_feas", "s_nov", "s_grd", "加权总分"],
                                       hrows)
                              + "\n\n注:该基线用于衡量 LLM 方案相对人类方案的绝对水平;"
                                "与上表 Sol_L 分数差值见 2.1c。"))
    crows = []
    for r in per_sample:
        rub, h = r.get("rubric"), r.get("rubric_human")
        if rub and h:
            row = [r["pdf_id"]]
            row += [f"{rub[k]}(LLM) / {h[k]}(Human)" for k in
                    ("targetedness", "feasibility", "novelty", "groundedness")]
            row.append(fmt(rub["weighted_total"] - h["weighted_total"], 2))
            crows.append(row)
    if crows:
        out.append(md_section("2.1c LLM-Sol vs 人类 Sol(Rubric 逐维对比与加权总分差)",
                              md_table(["样本", "tgt(LLM/H)", "feas(LLM/H)", "nov(LLM/H)",
                                        "grd(LLM/H)", "Δ total"], crows)))
    out.append(md_section("平均(mean)", md_table(
        ["s_tgt", "s_feas", "s_nov", "s_grd", "加权总分", "语义相似", "AspectRecall"],
        [[fmt(m["targetedness"]), fmt(m["feasibility"]), fmt(m["novelty"]),
          fmt(m["groundedness"]), fmt(m["weighted_total"], 2), fmt(m["semantic_sim"], 3),
          pct(m["aspect_recall"])]])
        + (f"\n\n**人类基线均值**: tgt={fmt(m['human']['targetedness'])} "
           f"feas={fmt(m['human']['feasibility'])} nov={fmt(m['human']['novelty'])} "
           f"grd={fmt(m['human']['groundedness'])} "
           f"total={fmt(m['human']['weighted_total'], 2)}" if m.get("human") else "")))
    out.append(md_section("Rubric 备注(每样本裁判理由节选)", "\n".join(
        f"- {r['pdf_id']}: {r['rubric']['reason'] if r['rubric'] else '未评分'}"
        for r in per_sample)))
    write_text(config.REPORTS_DIR / f"rq2_2{tag}.md", "\n".join(out))
    write_json(config.REPORTS_DIR / f"rq2_2{tag}.json",
               {"emb": emb_name, "per_sample": per_sample, "mean": m})


def _console(per_sample: List[dict]) -> None:
    m = _mean(per_sample)
    print(banner("RQ2-2 摘要 [Observation + Human RW -> Solution](完整报告: outputs/reports/rq2_2.md)"))
    for r in per_sample:
        rub = r["rubric"] or {}
        h = r["rubric_human"] or {}
        print(f"  {r['pdf_id']} | tgt={rub.get('targetedness', '-')} "
              f"feas={rub.get('feasibility', '-')} nov={rub.get('novelty', '-')} "
              f"grd={rub.get('groundedness', '-')} total={fmt(rub.get('weighted_total'), 2)} "
              f"| Human基线total={fmt(h.get('weighted_total'), 2)} "
              f"| cos={fmt(r['semantic_sim'], 3)} | "
              f"AspectRecall={pct(r['aspect_recall'])} ({r['aspect_covered']}/{len(r['aspects'])})")
    print("-- 平均 --")
    print(f"  tgt={fmt(m['targetedness'])} feas={fmt(m['feasibility'])} "
          f"nov={fmt(m['novelty'])} grd={fmt(m['groundedness'])} "
          f"total={fmt(m['weighted_total'], 2)} | cos={fmt(m['semantic_sim'], 3)} | "
          f"AspectRecall={pct(m['aspect_recall'])} "
          f"({m['aspect_covered']}/{m['aspect_total']})")
    if m.get("human") and m["human"]["weighted_total"] is not None:
        delta = fmt(m["weighted_total"] - m["human"]["weighted_total"], 2) \
            if m["weighted_total"] is not None else "-"
        print(f"  [人类 Sol 基线] total={fmt(m['human']['weighted_total'], 2)} "
              f"(tgt={fmt(m['human']['targetedness'])}, feas={fmt(m['human']['feasibility'])}, "
              f"nov={fmt(m['human']['novelty'])}, grd={fmt(m['human']['groundedness'])}) | "
              f"LLM−Human Δtotal={delta}")


if __name__ == "__main__":
    sys.exit(main())
