"""
====================================================
MinerU-PDF2md.py — 利用MinerU将PDF批量转为Markdown
====================================================

作用：
    将指定文件夹下的所有PDF文件，通过MinerU API提取文字，
    以同名 .md 文件保存到输出目录（目录不存在时自动创建）。

输入：
    PDF文件夹地址、输出文件夹地址（自动创建）、MinerU API-key

输出：
    1. 每个PDF对应一个 <pdf文件名>.md，放在输出目录下
    2. 对应关系文件 <输出目录>/pdf_mapping.jsonl：每个被处理的PDF一行JSON，
       记录 pdf_id（唯一辨识ID）、pdf_path（PDF原文路径）、
       md_path（生成的md路径）、status（success/skipped/failed）、time

功能特性：
    1. 批量并行处理（默认10线程）
    2. 断点续跑：已生成 .md 的PDF自动跳过
    3. 输出扁平化：所有md直接放在输出目录下
    4. 唯一ID映射：每个PDF基于其绝对路径生成唯一 pdf_id（同一文件重复
       运行ID不变），与原文路径、md路径一起以JSONL格式保存，便于溯源

依赖：
    pip install requests tqdm

用法示例：
    # 必填参数：PDF目录、输出目录、API-key
    python MinerU-PDF2md.py <pdf_dir> <output_dir> --api-key sk-xxxx

    # 或使用具名参数
    python MinerU-PDF2md.py --pdf-dir <pdf_dir> --output-dir <output_dir> --api-key sk-xxxx

    # API-key也可通过环境变量 MINERU_API_KEY 提供，此时可省略 --api-key

    # 控制并发与数量
    python MinerU-PDF2md.py <pdf_dir> <output_dir> --api-key sk-xxxx \
        --max-workers 5 --max 10
"""

import json
import time
import hashlib
import zipfile
import shutil
import argparse
import os
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from tqdm import tqdm


def generate_pdf_id(pdf_path: Path) -> str:
    """为PDF生成唯一辨识ID

    基于PDF绝对路径的sha256摘要（取前16位）：同一PDF文件重复运行时
    得到的ID相同，可跨运行稳定追踪；不同文件ID不会冲突。
    """
    abs_path = str(pdf_path.resolve())
    return hashlib.sha256(abs_path.encode("utf-8")).hexdigest()[:16]


class PdfMappingLogger:
    """记录 pdf_id ↔ PDF原文路径 ↔ MD输出路径，以JSONL格式追加保存（线程安全）

    每行一个被处理的PDF，JSON字段:
        pdf_id   : 唯一辨识ID（见 generate_pdf_id）
        pdf_path : PDF原文的绝对路径
        md_path  : 生成的Markdown绝对路径
        status   : success(新提取) / skipped(已存在而跳过) / failed(失败)
        time     : 记录时间
    """

    def __init__(self, jsonl_path: Path):
        self.jsonl_path = Path(jsonl_path)
        self._lock = Lock()

    def log(self, pdf_path: Path, md_path: Path, status: str) -> None:
        """追加一条映射记录到JSONL文件（多线程下串行写入）"""
        record = {
            "pdf_id": generate_pdf_id(pdf_path),
            "pdf_path": str(pdf_path.resolve()),
            "md_path": str(md_path.resolve()),
            "status": status,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with self.jsonl_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


class MinerUClient:
    """MinerU API客户端"""

    def __init__(self, token: str, base_url: str, model_version: str = "vlm"):
        self.base_url = base_url.rstrip("/")
        self.model_version = model_version
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def apply_upload_urls_batch(self, files):
        """申请上传URL"""
        url = f"{self.base_url}/file-urls/batch"
        resp = self.session.post(
            url,
            headers={"Content-Type": "application/json"},
            json={"files": files, "model_version": self.model_version},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(data)
        return data["data"]["batch_id"], data["data"]["file_urls"]

    def upload(self, presigned_url, file_path):
        """上传文件"""
        with file_path.open("rb") as f:
            r = requests.put(presigned_url, data=f)
        if r.status_code != 200:
            raise RuntimeError("Upload failed")

    def wait_batch(self, batch_id):
        """等待批次处理完成"""
        while True:
            r = self.session.get(
                f"{self.base_url}/extract-results/batch/{batch_id}"
            )
            data = r.json()
            if data.get("code") != 0:
                raise RuntimeError(data)

            results = data["data"]["extract_result"]
            states = [x["state"] for x in results]

            if results and all(s in ("done", "failed") for s in states):
                return data["data"]

            time.sleep(3)

    def download_and_extract(self, zip_url, out_dir):
        """下载并解压结果"""
        zip_path = out_dir / "tmp.zip"

        with self.session.get(zip_url, stream=True) as r:
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    f.write(chunk)

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(out_dir)

        zip_path.unlink()


def extract_single_pdf(client: MinerUClient, pdf_path: Path, output_dir: Path) -> str:
    """提取单个PDF文件，成功则保存 <pdf文件名>.md 到输出目录

    Args:
        client: MinerU API客户端
        pdf_path: PDF文件路径
        output_dir: md输出目录

    Returns:
        str: 处理状态 "success"(新提取成功) / "skipped"(已存在而跳过) / "failed"(失败)
    """
    md_filename = pdf_path.stem + ".md"
    md_path = output_dir / md_filename

    # 断点续跑：已存在则跳过
    if md_path.exists():
        print(f"  [Skip] 已存在: {md_filename}")
        return "skipped"

    try:
        print(f"  [Extract] {pdf_path.name}")

        # 调用MinerU API
        files_payload = [{"name": pdf_path.name, "data_id": pdf_path.stem}]
        batch_id, presigned_urls = client.apply_upload_urls_batch(files_payload)
        client.upload(presigned_urls[0], pdf_path)

        data = client.wait_batch(batch_id)
        result = data["extract_result"][0]

        if result["state"] != "done":
            raise RuntimeError(f"MinerU failed: {result}")

        # 下载结果到临时目录
        temp_dir = output_dir / f"temp_{pdf_path.stem}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        zip_url = result["full_zip_url"]
        client.download_and_extract(zip_url, temp_dir)

        # 查找full.md文件
        full_md = temp_dir / "full.md"
        if not full_md.exists():
            raise RuntimeError("No full.md found")

        # 移动到输出目录并重命名
        shutil.move(str(full_md), str(md_path))

        # 清理临时目录
        shutil.rmtree(temp_dir)

        print(f"  [OK] 提取成功: {md_filename}")
        return "success"

    except Exception as e:
        print(f"  [FAIL] 提取失败: {pdf_path.name}, 错误: {str(e)[:200]}")
        return "failed"


def extract_batch(
    pdf_dir: str,
    output_dir: str,
    api_key: str,
    base_url: str = "https://mineru.net/api/v4",
    model_version: str = "vlm",
    max_workers: int = 10,
    max_number: int = 0,
) -> dict:
    """批量提取PDF文件为Markdown

    Args:
        pdf_dir: PDF文件夹路径
        output_dir: md输出目录路径（不存在时自动创建）
        api_key: MinerU API-key
        base_url: MinerU API地址
        model_version: MinerU模型版本
        max_workers: 并行处理线程数
        max_number: 最大处理数量（0=处理全部）

    Returns:
        dict: 提取统计信息
    """
    pdf_dir = Path(pdf_dir)
    output_dir = Path(output_dir)

    # 校验输入目录
    if not pdf_dir.exists():
        print(f"[ERROR] PDF目录不存在: {pdf_dir}")
        return {"success": 0, "failed": 0, "skipped": 0}

    # 自动创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[Config] PDF输入目录: {pdf_dir}")
    print(f"[Config] MD输出目录: {output_dir}")

    # 获取PDF文件列表
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if max_number > 0:
        pdf_files = pdf_files[:max_number]

    print(f"\n[MinerU] 发现PDF文件: {len(pdf_files)} 个")

    if len(pdf_files) == 0:
        print("[WARN] 未找到PDF文件")
        return {"success": 0, "failed": 0, "skipped": 0}

    # 初始化MinerU客户端
    client = MinerUClient(
        token=api_key,
        base_url=base_url,
        model_version=model_version,
    )

    success_count = 0
    failed_count = 0
    skipped_count = 0
    failed_files = []

    # 映射日志：pdf_id ↔ PDF原文路径 ↔ MD路径，JSONL格式追加保存
    mapping_logger = PdfMappingLogger(output_dir / "pdf_mapping.jsonl")

    # 并行处理
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_pdf = {
            executor.submit(extract_single_pdf, client, pdf_path, output_dir): pdf_path
            for pdf_path in pdf_files
        }

        with tqdm(total=len(pdf_files), desc="MinerU提取进度") as pbar:
            for future in as_completed(future_to_pdf):
                pdf_path = future_to_pdf[future]
                md_path = output_dir / (pdf_path.stem + ".md")
                try:
                    status = future.result()

                    if status == "success":
                        success_count += 1
                    elif status == "skipped":
                        skipped_count += 1
                    else:
                        failed_count += 1
                        failed_files.append(pdf_path.name)

                    # 写入对应关系：pdf_id + 原文路径 + md路径
                    mapping_logger.log(pdf_path, md_path, status)
                except Exception as e:
                    failed_count += 1
                    failed_files.append(pdf_path.name)
                    mapping_logger.log(pdf_path, md_path, "failed")
                    print(f"\n[ERROR] {pdf_path.name}: {str(e)[:200]}")
                finally:
                    pbar.update(1)

    # 保存日志
    log_data = {
        "total": len(pdf_files),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "failed_files": failed_files,
        "pdf_dir": str(pdf_dir),
        "output_dir": str(output_dir),
    }

    log_path = output_dir / "extraction_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    print(f"\n[MinerU] 提取完成")
    print(f"  总计: {len(pdf_files)}")
    print(f"  新提取: {success_count}")
    print(f"  跳过: {skipped_count}")
    print(f"  失败: {failed_count}")
    print(f"  输出目录: {output_dir}")
    print(f"  日志文件: {log_path}")
    print(f"  ID映射文件: {mapping_logger.jsonl_path}")

    if failed_files:
        print(f"\n[WARN] 失败文件:")
        for f in failed_files:
            print(f"  - {f}")

    return log_data


def main():
    parser = argparse.ArgumentParser(
        description="MinerU-PDF2md: 利用MinerU将PDF批量提取文字为Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例：
  # 必填参数：PDF目录、输出目录、API-key（顺序位置参数）
  python MinerU-PDF2md.py <pdf_dir> <output_dir> --api-key sk-xxxx

  # 或使用具名参数
  python MinerU-PDF2md.py --pdf-dir <pdf_dir> --output-dir <output_dir> --api-key sk-xxxx

  # API-key也可通过环境变量 MINERU_API_KEY 提供（无需 --api-key）

  # 控制并发与数量
  python MinerU-PDF2md.py <pdf_dir> <output_dir> --api-key sk-xxxx --max-workers 5 --max 10
        """,
    )

    parser.add_argument("pdf_dir", nargs="?", default=None,
                        help="PDF文件夹路径（必填）")
    parser.add_argument("output_dir", nargs="?", default=None,
                        help="md输出目录路径，自动创建（必填）")
    parser.add_argument("--pdf-dir", "-p", dest="pdf_dir_opt", default=None,
                        help="PDF文件夹路径（与位置参数二选一）")
    parser.add_argument("--output-dir","-o", dest="output_dir_opt", default=None,
                        help="md输出目录路径，自动创建（与位置参数二选一）")
    parser.add_argument("--api-key", default='eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiIyNjQwMDcyNSIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc4MTc1NTE3NSwiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiMTg1OTE4MTI4NjkiLCJvcGVuSWQiOm51bGwsInV1aWQiOiJlYWMwYTJiNy1jOGQ3LTQxM2QtYjM5ZS1kMWRjNjUyOWM5ODciLCJlbWFpbCI6IjUwMjAyNTM3MDA3MkBzbWFpbC5uanUuZWR1LmNuIiwiZXhwIjoxNzg5NTMxMTc1fQ.zIteVB3jsmDwRd7ItbnCU4DJLuqhRkeLf_bV3JKZTjHyILchiZpLzjButnXFjPIIT8AJzD5twMFpCFSGIE-pcQ',
                        help="MinerU API-key（也可通过环境变量 MINERU_API_KEY 提供）")
    parser.add_argument("--base-url", default="https://mineru.net/api/v4",
                        help="MinerU API地址（默认: https://mineru.net/api/v4）")
    parser.add_argument("--model-version", default="vlm",
                        help="MinerU模型版本（默认: vlm）")
    parser.add_argument("--max-workers", type=int, default=10,
                        help="并行线程数（默认: 10）")
    parser.add_argument("--max", type=int, default=0,
                        help="最大处理数量，0=全部（默认: 0）")

    args = parser.parse_args()

    # 解析PDF目录（位置参数优先，其次具名参数）
    pdf_dir = args.pdf_dir or args.pdf_dir_opt
    output_dir = args.output_dir or args.output_dir_opt

    if not pdf_dir or not output_dir:
        parser.print_help()
        print("\n[ERROR] 缺少必填参数：PDF目录 和 输出目录")
        return

    # 解析API-key（命令行参数优先，其次环境变量）
    api_key = args.api_key or os.environ.get("MINERU_API_KEY")
    if not api_key:
        print("[ERROR] 缺少MinerU API-key，请通过 --api-key 或环境变量 MINERU_API_KEY 提供")
        return

    start_time = time.time()

    result = extract_batch(
        pdf_dir=pdf_dir,
        output_dir=output_dir,
        api_key=api_key,
        base_url=args.base_url,
        model_version=args.model_version,
        max_workers=args.max_workers,
        max_number=args.max,
    )

    elapsed = time.time() - start_time
    print(f"\n总耗时: {elapsed:.2f}秒 ({elapsed/60:.2f}分钟)")
    print(f"新提取: {result['success']} 个 | "
          f"跳过: {result['skipped']} 个 | "
          f"失败: {result['failed']} 个")


if __name__ == "__main__":
    main()
