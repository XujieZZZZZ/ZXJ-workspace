# -*- coding: utf-8 -*-
"""可视化任务(visual-test.md):LLM 生成相关工作(works/claims)相对人类基线的时间/空间分布。

对比口径(与评测一致,只读不改):
- 人类 GT   : data/human_data/<pdf_id>.json(related_works 含 claims 与 works)
- LLM(带检索): data/LLM_data/merged_llm_re_withsearch/<pdf_id>.json

两侧共有的论文(本次新增,图上标出;口径与 RQ2-1 完全一致,零新增计算):
- **只标"两边都有"的论文**:两侧 S2 解析到同一篇论文(同一 DOI 或 S2ID,L1 精确实体匹配)
  的才计入;语义近似(S_M 的 L2/L3)一律不算共有,不做任何标注;
- 匹配直接调用 rq2_1.match_levels 的 L1 判定(与 run_rq2_1.py 同一条代码路径),
  向量取本脚本已加载的同一份 SPECTER2 缓存,不新增任何编码/检索;
- 表现方式:两边都有的论文**直接画成绿色方块**(■,不区分来源侧);其余点仍是
  圆点且颜色语义不变(蓝=Human、橙=LLM,总图=论文色相);全 8 篇合计 16 篇;
- 每篇论文图与总图均标注;claims 无实体匹配口径,"共有"仅指两侧逐字相同的
  claim(实测 0 条,图中以文字给出)。

编码复用核对结论(不重复计算):
- works 的"现存编码"即评测管线 SPECTER2 向量:输入 = embedder.paper_doc_text(
  标题 + S2 解析摘要,无摘要仅标题),按文本哈希缓存于 outputs/cache/embeddings/
  (rq2_1.build_vectors 同口径)。逐条核对命中率:人类 works 366/366、
  LLM(withsearch) works 68/68、observation 8/8 全部命中既有缓存;
  本脚本 works/obs 只从磁盘缓存读取,零新增计算;
- claims 在既有评估管线中无向量(NLI/裁判路线),本次按同一编码器补充 280 条
  向量(结果落盘同一缓存目录,便于将来复用,不影响既有文件)。

输出(全部为新增文件): evaluator/outputs/visualization/ 下
  works_2d_<paper>.png / works_2d_overview.png
  claims_2d_<paper>.png / claims_2d_overview.png
  works_time_distribution.png / data_points.jsonl / README.md

用法:  python visualize_related_works.py    (在 evaluator/ 目录下运行)
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.lines import Line2D
from sklearn.manifold import TSNE

import config
import dataio
import metrics_calc as mc
import rq2_1                     # 复用其 L1 同篇判定(与 run_rq2_1.py 同一条口径)
from embedder import Specter2Embedder, paper_doc_text
from utils import log

# --------------------------------------------------------------------------- #
# 全局设置
# --------------------------------------------------------------------------- #
from matplotlib import font_manager
for _fp in ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
    if Path(_fp).exists():
        font_manager.fontManager.addfont(_fp)
# 中英文混排:DejaVu Sans 负责拉丁/数字,Droid Sans Fallback 兜底中文字形
rcParams["font.sans-serif"] = ["DejaVu Sans", "Droid Sans Fallback"]
rcParams["font.family"] = "sans-serif"
rcParams["axes.unicode_minus"] = False
rcParams["savefig.bbox"] = "tight"
rcParams["savefig.dpi"] = 200

COL_H = "#0072B2"            # 人类
COL_L = "#D55E00"            # LLM(with search)
COL_OBS = "#F2B134"          # Observation 锚点 ★
COL_OBS_EDGE = "#5B4A00"
COL_TXT = "#333333"
COL_SHARE = "#009E73"        # "两边都有"的论文:绿色方块(Okabe-Ito 色盲友好绿,与蓝/橙及论文色相均可区分)

SHARED = 1                   # 两侧解析到同一篇论文(DOI/S2ID 精确匹配)= 图上绿方块
MARK_SHARED = "s"            # 共有论文的标记形状:方形(普通点仍为圆形)

VIZ_DIR = config.OUTPUTS_DIR / "visualization"
EMB_LABEL = "SPECTER2"            # 图上标注的编码器名(命令行 --emb 切换)
FIG_W, FIG_H = 9.2, 8.0      # 每论文图幅(英寸)
TSNE_SEED = 42


# --------------------------------------------------------------------------- #
# 一、数据装载
# --------------------------------------------------------------------------- #
class Instance:
    """一个可视化实例(work/claim/observation),携带编码文本与展示元数据。"""
    __slots__ = ("kind", "side", "pdf_id", "text", "title", "year", "vec",
                 "norm", "entity", "share", "share_with")

    def __init__(self, kind: str, side: str, pdf_id: str, text: str,
                 title: str = None, year: int = None, norm: str = None):
        self.kind = kind          # 'work' | 'claim' | 'obs'
        self.side = side          # 'H' 人类 | 'L' LLM(withsearch) | 'O' observation
        self.pdf_id = pdf_id
        self.text = text          # 编码用文本(与评测管线逐字一致)
        self.title = title        # works:论文标题(展示)
        self.year = year          # works:发表年份(时间分布)
        self.norm = norm          # works:规范化标题(= dataio.unique_works 的键)
        self.entity = None        # works:S2 规范实体键(paperId/DOI)——同一篇论文去重用
        self.vec = None
        self.share = 0            # 1 = 两侧引用同一篇论文(见 mark_shared_*);0 = 非共有
        self.share_with = []      # 对侧那篇同论文的标题(落盘溯源)

    @property
    def tag(self) -> str:
        from utils import text_hash
        return f"{self.side}:{self.kind}:{self.pdf_id}:{text_hash(self.text)}"

    def __repr__(self):
        return f"<{self.side} {self.kind} {self.pdf_id} {str(self.title or self.text)[:40]}>"


def load_resolution() -> dict:
    """读取既有 S2 解析缓存(解析结果已在评测期落盘,不联网)。"""
    res = {}
    for line in config.CACHE_DIR.joinpath("s2_resolution.jsonl").open(encoding="utf-8"):
        d = json.loads(line)
        res[d["_key"]] = d
    return res


def work_embed_text(w: dict, res: dict) -> str:
    """work 的编码文本——与 rq2_1.build_vectors 逐字一致:
    S2 解析成功取规范标题+摘要,否则回退数据自带标题(仅标题)。"""
    rec = res.get(w["_norm"]) or {}
    p = (rec.get("s2_paper") or {}) if rec.get("status") == "found" else {}
    return paper_doc_text(p.get("title") or w["title"], p.get("abstract"))


def work_entity(w: dict, res: dict) -> str:
    """work 的 S2 规范实体键(判定"是不是同一篇论文"的键):paperId 优先,退化 DOI,
    再退化规范化标题。两侧标题写法可能不同(如 FPGA-based / FPGA based),解析到同一篇
    则 paperId 相同——统计共有论文数/年份时按此去重,避免同一篇被算两次。"""
    p = (res.get(w["_norm"]) or {}).get("s2_paper") or {}
    return p.get("paperId") or (p.get("doi") or "").lower() or f"norm:{w['_norm']}"


def work_year_of(w: dict, res: dict) -> int | None:
    """work 年份:人类取数据自带;LLM 取 S2 解析年份(LLM 生成文件无 year 字段)。"""
    y = w.get("year")
    if y is None:
        rec = res.get(w["_norm"]) or {}
        if rec.get("status") == "found":
            y = (rec.get("s2_paper") or {}).get("year")
    return int(y) if y is not None else None


def collect() -> tuple:
    """收集 8 篇论文的 works / claims / observation 实例列表。

    works 文档内按唯一标题(集合语义,同 dataio.unique_works);
    claims 为段落内全部句子(同 dataio.all_claims,不去重);obs 每篇 1 条。"""
    res = load_resolution()
    works, claims, obs = [], [], []
    for pdf_id in dataio.list_pdf_ids():
        doc_h = dataio.load_doc(dataio.SET_GT, pdf_id)
        doc_l = dataio.load_doc(dataio.SET_WS, pdf_id)
        for side, doc in (("H", doc_h), ("L", doc_l)):
            for w in dataio.unique_works(doc):
                works.append(Instance("work", side, pdf_id,
                                      work_embed_text(w, res),
                                      title=(w.get("title") or "").strip(),
                                      year=work_year_of(w, res),
                                      norm=w["_norm"]))
            for c in dataio.all_claims(doc):
                claims.append(Instance("claim", side, pdf_id, (c or "").strip()))
        obs.append(Instance("obs", "O", pdf_id, (doc_h["observation"] or "").strip()))
    return works, claims, obs, res


# --------------------------------------------------------------------------- #
# 一(补)、两侧共有部分标注(works:同一篇论文;claims:逐字相同的句子)
# --------------------------------------------------------------------------- #
def mark_shared_works(works: list, res: dict) -> dict:
    """把"两边都有"的论文标到 work 实例上,返回逐论文计数(图例/日志用)。

    只认**同一篇论文**:匹配走 rq2_1.match_levels(与 run_rq2_1.py 同一条代码路径、
    同一份 SPECTER2 向量缓存),仅取 L1(两侧 S2 解析到同一 DOI/S2ID)的配对;
    L2/L3 的语义近似匹配**不计入共有**、不标注。向量直接取实例上已加载的缓存向量,
    零新增计算。返回:
      {"l1_pairs": 同一篇论文的配对数, "n_papers": 去重后的论文数(= 图上绿方块数),
       "per_pid": {pdf_id: {"l1_pairs": n, "titles": [共有论文标题]}}}
    """
    by_key = {}
    for it in works:
        by_key[(it.pdf_id, it.side, it.norm)] = it
    stat = {"l1_pairs": 0, "per_pid": {}}
    for pdf_id in dataio.list_pdf_ids():
        doc_h = dataio.load_doc(dataio.SET_GT, pdf_id)
        doc_l = dataio.load_doc(dataio.SET_WS, pdf_id)
        H, L = dataio.unique_works(doc_h), dataio.unique_works(doc_l)
        vecs = {"vec": {}, "v_obs": None}
        for tag, W in (("H", H), ("L", L)):
            for w in W:
                it = by_key.get((pdf_id, tag, w["_norm"]))
                if it is not None:
                    it.entity = work_entity(w, res)
                    if it.vec is not None:
                        vecs["vec"][f"{tag}:{w['_norm']}"] = it.vec
        M = rq2_1.match_levels(doc_h, doc_l, res, vecs)["M"]
        pid = {"l1_pairs": 0, "titles": []}
        ents = set()
        for i, row in enumerate(M):
            h_it = by_key.get((pdf_id, "H", H[i]["_norm"]))
            for j, lvl in enumerate(row):
                if lvl != SHARED:              # 只认"同一篇论文",语义匹配不标注
                    continue
                l_it = by_key.get((pdf_id, "L", L[j]["_norm"]))
                for it, other in ((h_it, L[j]["title"]), (l_it, H[i]["title"])):
                    if it is not None:
                        it.share = SHARED
                        if other not in it.share_with:
                            it.share_with.append(other)
                pid["l1_pairs"] += 1
                ents.add(h_it.entity if h_it is not None else H[i]["_norm"])
                pid["titles"].append(f"H: {H[i]['title']}  ||  L: {L[j]['title']}")
        stat["l1_pairs"] += pid["l1_pairs"]
        stat["n_papers"] = stat.get("n_papers", 0) + len(ents)   # 图上绿方块数
        stat["per_pid"][pdf_id] = pid
    return stat


def mark_shared_claims(claims: list) -> dict:
    """claims 的"共有"= 两侧逐字相同的 claim(claims 无实体匹配口径,实测 0 条)。"""
    stat = {"l1_pairs": 0, "per_pid": {}}
    for pdf_id in dataio.list_pdf_ids():
        side_txt = {"H": set(), "L": set()}
        for it in claims:
            if it.pdf_id == pdf_id:
                side_txt[it.side].add(it.text)
        both = side_txt["H"] & side_txt["L"]
        for it in claims:
            if it.pdf_id == pdf_id and it.text in both:
                it.share = SHARED
        stat["l1_pairs"] += len(both)
        stat["per_pid"][pdf_id] = {"l1_pairs": len(both), "titles": sorted(both)}
    return stat


# --------------------------------------------------------------------------- #
# 二、向量:复用既有磁盘缓存;缺失(仅 claims)时补编码并落盘
# --------------------------------------------------------------------------- #
def embed_all(insts: list, emb: Specter2Embedder, label: str) -> None:
    """批量取向量。统计缓存命中率:命中=直接读 npy(不加载模型);未命中=GPU 补算。"""
    from utils import text_hash
    n_hit = n_miss = 0
    for it in insts:
        h = text_hash(it.text)
        if emb.emb_dir.joinpath(h[:2], h + ".npy").exists():
            n_hit += 1
        else:
            n_miss += 1
        it.vec = emb.encode_cached(it.text)     # 命中读盘 / 未命中计算后落盘
    if n_miss:
        log(f"[{label}] 缓存命中 {n_hit},新增编码 {n_miss} 条")
    else:
        log(f"[{label}] 全部 {n_hit} 条命中既有缓存(零新增计算)")


# --------------------------------------------------------------------------- #
# 三、t-SNE 布局(相同向量一次拟合,共享坐标)
# --------------------------------------------------------------------------- #
def tsne_layout(insts: list, perp: int | None = None) -> dict:
    """对实例集合做 t-SNE:先对唯一向量拟合,再回填每个实例的 (x, y)。"""
    vecs = np.stack([np.asarray(it.vec, dtype=np.float32) for it in insts])
    uniq, idx, inv = np.unique(vecs, axis=0, return_index=True, return_inverse=True)
    order = np.argsort(idx)                     # 按首次出现排序,保持稳定
    remap = {old: new for new, old in enumerate(order)}
    gids = np.array([remap[i] for i in inv])
    n_u = len(order)
    ppl = perp or int(min(30, max(6, round(float(np.sqrt(n_u))))))
    if ppl >= n_u - 1:
        ppl = max(2, n_u - 2)
    xy_u = TSNE(n_components=2, perplexity=ppl, init="pca", learning_rate="auto",
                max_iter=2000, random_state=TSNE_SEED).fit_transform(vecs[order])
    return {it.tag: xy_u[g] for it, g in zip(insts, gids)}


def overview_layout(insts: list, emb: Specter2Embedder) -> tuple:
    """总图双层合成布局(works/claims 通用)。

    动机:全局单空间 t-SNE 下,被引 works 按"被引论文主题"而非"引用论文"分布
    (高维按论文分组的 silhouette≈0),任何 t-SNE 参数都会把每篇论文的点撕裂到两团。
    因此总图采用两层布局,保证"同一论文必在同一区域、颜色归属无歧义":
    - 层1(岛间):以 8 篇论文的 Observation 向量做 PCA 得到岛心——Observation 是每篇
      论文的主题锚,岛间距≈论文主题相似度;
    - 层2(岛内):每篇论文自己的 H+L 点做局部 t-SNE,归一化后铺在以岛心为圆心、
      半径 R 的范围内(保留岛内真实邻近结构);
    - 每篇的 Observation ★ 直接落在岛心。
    返回 {tag -> (x,y)} 及岛屿半径 R(数据坐标,供重合点展开)。"""
    pid_list = dataio.list_pdf_ids()
    obs_list = [it for it in insts if it.kind == "obs"]
    # ---- 岛心:Observation PCA 初值 -> z-score -> 最小间距排斥展开 ----
    # (观察向量可能非常接近(如 Can't-Be-Late 与 TXN),若直接取全局最小距
    #  决定岛半径会把所有岛压成点;故固定岛半径 R,并对过近岛心做确定性排斥)
    from sklearn.decomposition import PCA
    O = np.stack([np.asarray(it.vec, dtype=np.float32) for it in obs_list])
    cen = PCA(n_components=2, random_state=TSNE_SEED).fit_transform(O)
    for d in range(2):
        sd = float(cen[:, d].std()) or 1.0
        cen[:, d] = (cen[:, d] - cen[:, d].mean()) / sd           # z-score
    R = 0.20
    D_MIN = 0.55                                                  # 岛心最小间距(>2R)
    for _ in range(300):
        moved = False
        for i in range(len(cen)):
            for j in range(i + 1, len(cen)):
                vec = cen[i] - cen[j]
                dist = float(np.linalg.norm(vec))
                if dist < D_MIN and dist > 1e-9:
                    push = (D_MIN - dist) / 2
                    cen[i] += vec / dist * push
                    cen[j] -= vec / dist * push
                    moved = True
        if not moved:
            break
    for d in range(2):                                            # 收敛后整体居中收拢
        cen[:, d] = (cen[:, d] - cen[:, d].mean()) * 0.9
    centers = dict(zip(pid_list, cen))
    # ---- 岛内:局部 t-SNE -> 归一化到半径 R 的圆盘 ----
    xy = {}
    for pid in pid_list:
        island = [it for it in insts if it.pdf_id == pid and it.side in ("H", "L")]
        if not island:
            continue
        local = tsne_layout(island)            # 复用:唯一向量拟合 + 标签回填
        arr = np.array([local[it.tag] for it in island])
        r = float(np.abs(arr).max()) or 1.0
        c = centers[pid]
        for it in island:
            xy[it.tag] = (c[0] + (local[it.tag][0] / r) * R,
                          c[1] + (local[it.tag][1] / r) * R)
    for it in obs_list:                        # Observation 放岛心
        xy[it.tag] = centers[it.pdf_id]
    return xy, R


def expand_duplicates(insts: list, xy: dict, dup_r: float) -> dict:
    """同一坐标重合的实例(同向量/同文本)沿小圆展开,避免互相遮挡。"""
    groups = defaultdict(list)
    for it in insts:
        groups[tuple(np.round(xy[it.tag], 6))].append(it)
    out = dict(xy)
    if dup_r > 0:
        for g, members in groups.items():
            if len(members) <= 1:
                continue
            ang = np.linspace(0, 2 * np.pi, len(members), endpoint=False) + TSNE_SEED
            for it, a in zip(members, ang):
                out[it.tag] = (g[0] + dup_r * np.cos(a), g[1] + dup_r * np.sin(a))
    return out


def dup_radius(xy: dict, s: float, fig_w: float, ax_frac: float = 0.86) -> float:
    """按散点标记尺寸换算"重合点展开半径"(数据坐标)。"""
    coords = np.array(list(xy.values()))
    span = max(float(coords[:, 0].max() - coords[:, 0].min()),
               float(coords[:, 1].max() - coords[:, 1].min()), 1e-9)
    d_data = float(np.sqrt(s)) / 72.0 / (ax_frac * fig_w) * span   # 标记直径(数据单位)
    return max(d_data * 0.55, span * 3e-4)


# --------------------------------------------------------------------------- #
# 四、绘制
# --------------------------------------------------------------------------- #
def hide_axes(ax) -> None:
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)


def draw_obs(ax, xy, s: float, color: str = COL_OBS, edge: str = COL_OBS_EDGE,
             label: str = "Observation") -> None:
    """Observation 锚点(★)。只绘制参与布局的 obs 实例。"""
    pts = [(k, v) for k, v in xy.items() if k.startswith("O:")]
    if pts:
        ax.scatter([v[0] for _, v in pts], [v[1] for _, v in pts], s=s, marker="*",
                   c=color, edgecolors=edge, linewidths=0.8, zorder=9, label=label)


def shared_points(insts: list, xy: dict) -> list:
    """共有论文在图上各自的落点:每篇论文一个绿方块。

    同一篇论文在 H/L 两侧各有一个实例,两者编码文本相同(同篇 -> 同向量 -> 同坐标,
    仅被 expand_duplicates 沿小圆环摊开),这里按 S2 实体合并、取二者中点 = 原始坐标,
    故"一个方块 = 一篇两边都有的论文"。返回 [(x, y), ...]。"""
    groups = defaultdict(list)
    for it in insts:
        if it.share == SHARED:
            groups[(it.pdf_id, it.entity or it.norm)].append(xy[it.tag])
    return [tuple(np.mean(v, axis=0)) for v in groups.values()]


def share_legend_handle(shared: dict, kind: str) -> Line2D:
    """共有论文的图例色块(绿色方块):形状+颜色都表示"两边都有",不区分来源侧。"""
    unit = "papers" if kind == "work" else "claims"
    return Line2D([0], [0], marker=MARK_SHARED, color="none", markerfacecolor=COL_SHARE,
                  markeredgecolor="white", markeredgewidth=0.6, markersize=9,
                  label=f"both sides, same paper (n={shared['l1_pairs']} {unit})"
                  if kind == "work" else
                  f"both sides, identical text (n={shared['l1_pairs']} {unit})")


def draw_space_paper(insts, emb, kind: str, pname: str, shared: dict) -> tuple:
    """每篇论文一张图:Human 色点 vs LLM(with search)色点,同空间 t-SNE。

    圆点=只有一侧(蓝 Human / 橙 LLM),绿色方块=两边都引用同一篇论文(每篇一个方块,
    不区分侧);claims 的"共有"指两侧逐字相同(实测 0 条)。"""
    kind_cn = {"work": "Works", "claim": "Claims"}[kind]
    embed_all(insts, emb, f"{kind}:{pname}")
    xy0 = tsne_layout(insts)
    s_dot = 130
    dup_r = dup_radius(xy0, s_dot, FIG_W)
    xy = expand_duplicates(insts, xy0, dup_r)

    n_h = sum(1 for it in insts if it.side == "H")
    n_l = sum(1 for it in insts if it.side == "L")
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    hide_axes(ax)
    # 圆点=只有一侧(蓝 Human / 橙 LLM),绿方块=两边都有的同一篇论文(不区分侧)
    for side, col in (("H", COL_H), ("L", COL_L)):
        ps = [it for it in insts if it.side == side and it.share != SHARED]
        if ps:
            ax.scatter([xy[it.tag][0] for it in ps], [xy[it.tag][1] for it in ps],
                       s=s_dot, c=col, alpha=0.92, marker="o",
                       edgecolors="white", linewidths=0.4, zorder=4,
                       label=f"{'Human' if side == 'H' else 'LLM (with search)'}"
                             f", one side only (n={len(ps)})")
    pts = shared_points(insts, xy)
    if pts:
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=s_dot * 1.30,
                   marker=MARK_SHARED, c=COL_SHARE, edgecolors="white", linewidths=0.4,
                   zorder=5, label=f"both sides, same paper (n={len(pts)})")
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False,
              fontsize=11.5, borderaxespad=0.2)
    draw_obs(ax, xy, s=320)
    ax.set_aspect("equal")
    # 说明文字分两行:图例在轴外,轴宽有限,单行过长会被画布裁掉
    cap = (f"green square = cited by both sides (same paper; n={shared['l1_pairs']})"
           if kind == "work" else
           f"green square = identical claim text on both sides (n={shared['l1_pairs']})")
    ax.set_title(f"{kind_cn} semantic space - {pname}", fontsize=18, color=COL_TXT, pad=12)
    ax.set_xlabel(f"{EMB_LABEL} embeddings + t-SNE\n{cap}",
                  fontsize=10.5, color="#666666", labelpad=6)
    fname = f"{kind}s_2d_{pname}.png"
    fig.savefig(VIZ_DIR / fname)
    plt.close(fig)
    log(f"图已输出: {VIZ_DIR / fname}")
    return fname, xy


def draw_space_overview(insts, emb, kind: str, paper_names: dict, shared: dict) -> tuple:
    """8 篇论文总图:颜色=论文(8 色相),实心圆=Human / 空心圆=LLM(with search)。

    布局:双层合成布局(见 overview_layout)——每个论文是独立"岛屿",岛间按
    Observation 相似度排列,岛内为各自局部 t-SNE;保证同论文的点必在同一区域,
    颜色归属无歧义。点形语义:实心圆=Human、空心圆=LLM(with search)、**绿色方块=两边都有的
    同一篇论文**(每篇一个,不区分侧)、★=岛心 Observation。
    """
    kind_cn = {"work": "Works", "claim": "Claims"}[kind]
    embed_all(insts, emb, f"{kind}:overview")
    xy, _ = overview_layout(insts, emb)
    s_dot = 58 if kind == "work" else 66
    dup_r = dup_radius(xy, s_dot, 11.5, ax_frac=0.92)
    xy = expand_duplicates(insts, xy, dup_r)

    pid_list = dataio.list_pdf_ids()
    # 8 个高区分度色相:tab10 索引 0-6 + 9(跳过 7 灰、8 黄绿易与空心混淆)
    paper_colors = plt.cm.tab10([0, 1, 2, 3, 4, 5, 6, 9])
    fig, ax = plt.subplots(figsize=(11.5, 9.0))
    hide_axes(ax)
    # ---- 逐论文绘制:Human 实心圆 / LLM 空心圆(同色相);两边都有的论文另画绿方块 ----
    for i, pid in enumerate(pid_list):
        col = paper_colors[i]
        ph = [it for it in insts if it.pdf_id == pid and it.side == "H" and it.share != SHARED]
        pl = [it for it in insts if it.pdf_id == pid and it.side == "L" and it.share != SHARED]
        if ph:
            ax.scatter([xy[it.tag][0] for it in ph], [xy[it.tag][1] for it in ph],
                       s=s_dot, c=[col], alpha=0.92, edgecolors="white", linewidths=0.15,
                       zorder=3)
        if pl:
            ax.scatter([xy[it.tag][0] for it in pl], [xy[it.tag][1] for it in pl],
                       s=s_dot * 0.96, facecolors="white", edgecolors=[col],
                       linewidths=1.9, alpha=0.95, zorder=3.2)
    pts = shared_points(insts, xy)
    if pts:                       # 两边都有的论文:绿方块(不区分来源侧)
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=s_dot * 1.45,
                   marker=MARK_SHARED, c=COL_SHARE, edgecolors="white", linewidths=0.5,
                   zorder=4.5)
    draw_obs(ax, xy, s=230, color="#222222", edge="white", label="Observation")
    ax.set_aspect("equal")
    ax.set_title(f"All 8 papers - {kind_cn} overview ({EMB_LABEL} + t-SNE): "
                 f"color = paper, circle = one side, green square = both sides",
                 fontsize=16, color=COL_TXT, pad=12)
    # ---- 右侧图例:来源(灰圆) + 共有绿方块 + 论文色相(带各自 H/L/共有计数) ----
    n_h_all = sum(1 for it in insts if it.side == "H")
    n_l_all = sum(1 for it in insts if it.side == "L")
    handles = [Line2D([0], [0], marker="o", color="#555555", markerfacecolor="#555555",
                      markersize=9, label=f"solid = Human (n={n_h_all})"),
               Line2D([0], [0], marker="o", color="#555555", markerfacecolor="white",
                      markeredgecolor="#555555", markeredgewidth=1.5, markersize=9,
                      label=f"hollow = LLM with search (n={n_l_all})"),
               Line2D([0], [0], marker="*", color="#222222", markersize=13,
                      label="Observation")]
    if shared["l1_pairs"]:        # 确有共有项时才给图例(claims 实测 0 条,不占位)
        handles.insert(2, share_legend_handle(shared, kind))
    for i, pid in enumerate(pid_list):
        col = paper_colors[i]
        n_h = sum(1 for it in insts if it.pdf_id == pid and it.side == "H")
        n_l = sum(1 for it in insts if it.pdf_id == pid and it.side == "L")
        n_s = shared["per_pid"].get(pid, {}).get("l1_pairs", 0)
        handles.append(Line2D([0], [0], marker="o", color="w", markerfacecolor=col,
                              markeredgecolor="none", markersize=9,
                              label=f"{i + 1}  {paper_names.get(pid, pid)}   "
                                    f"H {n_h}  /  L {n_l}  /  both {n_s}"))
    ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.005, 0.5),
              frameon=False, fontsize=9, borderaxespad=0.2, labelspacing=1.05)
    fname = f"{kind}s_2d_overview.png"
    fig.savefig(VIZ_DIR / fname)
    plt.close(fig)
    log(f"图已输出: {VIZ_DIR / fname}")
    return fname, xy


def shared_work_years(works: list) -> list:
    """两侧共有的论文(L1)的年份——按 S2 实体去重(同一篇在 H/L 两侧各有一个实例)。"""
    seen: dict = {}
    for it in works:
        if it.share != SHARED:
            continue
        key = (it.pdf_id, it.entity or it.norm)
        if key not in seen or seen[key] is None:
            seen[key] = it.year
    return sorted(int(y) for y in seen.values() if y is not None)


def draw_time_distribution(works: list) -> str:
    """归一化发表年份分布(人类 works 远多于 LLM,故按各自数量归一为比例)。

    第三条曲线 = 两侧共有论文(L1,同一篇论文)的年份分布,用来回答"共有的部分是
    经典老论文还是近期工作"。
    """
    y_h = sorted(int(it.year) for it in works if it.side == "H" and it.year is not None)
    y_l = sorted(int(it.year) for it in works if it.side == "L" and it.year is not None)
    y_s = shared_work_years(works)
    lo, hi = int(min(min(y_h), min(y_l))) - 1, int(max(max(y_h), max(y_l))) + 1
    edges = np.arange(lo, hi + 1, dtype=float)
    h_h, _ = np.histogram(y_h, bins=edges, weights=np.full(len(y_h), 1 / len(y_h)))
    h_l, _ = np.histogram(y_l, bins=edges, weights=np.full(len(y_l), 1 / len(y_l)))

    fig, ax = plt.subplots(figsize=(11.5, 6.2))
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(colors="#555555")
    ax.grid(axis="y", color="#E8E8E8", lw=0.7, zorder=0)
    ax.stairs(h_h, edges, fill=True, color=COL_H, alpha=0.30, linewidth=2.0, zorder=3,
              label=f"Human works (n={len(y_h)})")
    ax.stairs(h_l, edges, fill=True, color=COL_L, alpha=0.30, linewidth=2.0, zorder=3,
              label=f"LLM works, with search (n={len(y_l)})")
    if y_s:   # 两侧共有(同一篇论文)的年份分布:黑色描边台阶,不填充
        h_s, _ = np.histogram(y_s, bins=edges, weights=np.full(len(y_s), 1 / len(y_s)))
        ax.stairs(h_s, edges, fill=False, color=COL_SHARE, linewidth=2.4, zorder=5,
                  label=f"cited by both sides, same paper (n={len(y_s)})")
    for ys, col in [(y_h, COL_H), (y_l, COL_L)] + ([(y_s, COL_SHARE)] if y_s else []):
        ax.axvline(np.median(ys), color=col, lw=1.2, ls="--", alpha=0.7, zorder=2)
    n_miss = sum(1 for it in works if it.side == "L" and it.kind == "work" and it.year is None)
    rr_h, _ = mc.recency_ratio(y_h)
    rr_l, _ = mc.recency_ratio(y_l)
    w1, _, _ = mc.w1_cdf_distance(y_h, y_l)
    stat = (f"Human:  median {np.median(y_h):.0f}  |  recent-3y share {rr_h:.1%}\n"
            f"LLM:    median {np.median(y_l):.0f}  |  recent-3y share {rr_l:.1%}\n"
            f"distribution gap W1 (EMD) = {w1:.2f} yrs")
    if y_s:
        rr_s, _ = mc.recency_ratio(y_s)
        stat += (f"\nboth sides (same paper): median {np.median(y_s):.0f}  |  "
                 f"recent-3y share {rr_s:.1%}")
    if n_miss:
        stat += f"\nnote: {n_miss} LLM works omitted (not found on S2)"
    # 统计框放左上空白区(1960–1995 上方无数据),避开右侧高柱
    ax.text(0.02, 0.76, stat, transform=ax.transAxes, ha="left", va="top", fontsize=9.5,
            color="#444444", bbox=dict(boxstyle="round,pad=0.5", fc="#FAFAFA", ec="#D5D5D5", lw=0.8))
    ax.legend(loc="upper left", frameon=False, fontsize=12)
    ax.set_xlim(lo - 0.5, hi + 0.5)
    ax.set_xlabel("Publication year", fontsize=12.5)
    ax.set_ylabel("Normalized fraction of works per series", fontsize=12.5)
    ax.set_title("Publication-year distribution of related works (normalized): "
                 "Human, LLM (with search), and shared",
                 fontsize=17, color=COL_TXT, pad=14)
    fname = "works_time_distribution.png"
    fig.savefig(VIZ_DIR / fname)
    plt.close(fig)
    log(f"图已输出: {VIZ_DIR / fname}")
    return fname


# --------------------------------------------------------------------------- #
# 五、主流程 + 数据落盘
# --------------------------------------------------------------------------- #
def dump_points(records: list) -> None:
    with (VIZ_DIR / "data_points.jsonl").open("w", encoding="utf-8") as f:
        for fname, insts, xy in records:
            for it in insts:
                row = {"fig": fname, "kind": it.kind, "side": it.side, "pdf_id": it.pdf_id,
                       "emb": EMB_LABEL, "title": it.title, "year": it.year,
                       "share": it.share,        # 1 = 两边都有(同一篇论文/逐字相同 claim)
                       "share_with": it.share_with,
                       "text": (it.text or "")[:500]}
                if it.tag in xy:
                    row["x"], row["y"] = map(float, xy[it.tag])
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def paper_names() -> dict:
    """pdf_id -> 论文简称(pdf_mapping.jsonl 的 pdf 文件名,退化用 pdf_id)。"""
    names = {}
    pdf_map = config.DATA_DIR / "pdf_mapping.jsonl"
    if pdf_map.exists():
        for line in pdf_map.open(encoding="utf-8"):
            d = json.loads(line)
            nm = os.path.basename(d.get("pdf_path") or "").replace(".pdf", "") or d["pdf_id"]
            names[d["pdf_id"]] = nm
    for pid in dataio.list_pdf_ids():
        names.setdefault(pid, pid)
    return names


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="works/claims 空间与时间分布可视化(visual-test.md)")
    ap.add_argument("--emb", default=config.EMB_DEFAULT, choices=list(config.EMB_CHOICES),
                    help="语义编码器(specter2_base 保留既有结果目录;其余编码器输出到独立目录)")
    args = ap.parse_args()
    global VIZ_DIR, EMB_LABEL
    emb_label_map = {"specter2_base": "SPECTER2", "scibert": "SciBERT", "specter2": "SPECTER2-adapter"}
    EMB_LABEL = emb_label_map[args.emb]
    VIZ_DIR = config.OUTPUTS_DIR / ("visualization" if args.emb == config.EMB_DEFAULT
                                    else f"visualization_{args.emb}")
    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    pnames = paper_names()
    log(f"编码器: {args.emb}({EMB_LABEL}) -> 输出目录 {VIZ_DIR.name}")
    log("装载数据与 S2 解析缓存…")
    works, claims, obs, res = collect()
    log(f"实例统计 —— works: Human {sum(1 for i in works if i.side == 'H')} / "
        f"LLM {sum(1 for i in works if i.side == 'L')}; "
        f"claims: Human {sum(1 for i in claims if i.side == 'H')} / "
        f"LLM {sum(1 for i in claims if i.side == 'L')}")

    _spec = config.EMB_CHOICES[args.emb]
    emb = Specter2Embedder(model_dir=_spec[0], adapter_dir=_spec[2], pooling=_spec[3],
                           name=None if args.emb == config.EMB_DEFAULT else args.emb)
    # 0) 共有部分标注:works 取 RQ2-1 的 L1 同篇判定(先备好向量,全部命中缓存)
    embed_all(works, emb, "works(共有标注用)")
    sh_work = mark_shared_works(works, res)
    sh_claim = mark_shared_claims(claims)
    log(f"两侧共有(works): 同一篇论文(DOI/S2ID 相同) {sh_work['n_papers']} 篇"
        f"-> 每图每篇画一个绿方块(配对数 {sh_work['l1_pairs']})")
    log(f"两侧共有(claims): 逐字相同 {sh_claim['l1_pairs']} 条")

    records = []
    # 1) 每篇论文的 works / claims 图
    for pdf_id in dataio.list_pdf_ids():
        pname = "".join(ch for ch in pnames[pdf_id] if ch.isalnum() or ch in "-_") or pdf_id
        for kind, pool, sh in (("work", works, sh_work), ("claim", claims, sh_claim)):
            insts = [it for it in pool if it.pdf_id == pdf_id] + [o for o in obs if o.pdf_id == pdf_id]
            fn, xy = draw_space_paper(insts, emb, kind, pname,
                                      sh["per_pid"].get(pdf_id) or {"l1_pairs": 0})
            records.append((fn, insts, xy))
    # 2) 总图
    for kind, pool, sh in (("work", works, sh_work), ("claim", claims, sh_claim)):
        insts = pool + obs
        fn, xy = draw_space_overview(insts, emb, kind, pnames, sh)
        records.append((fn, insts, xy))
    # 3) 时间分布
    fn = draw_time_distribution(works)
    records.append((fn, works, {}))
    dump_points(records)
    log(f"全部完成,输出目录: {VIZ_DIR}")


if __name__ == "__main__":
    main()
