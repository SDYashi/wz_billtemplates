#!/usr/bin/env python3

import argparse
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, List

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://testing.mpwin.co.in/pdfbills"

# =========================================================
# ✅ API FUNCTIONS
# =========================================================
def send_request_v1(html_content: str) -> requests.Response:
    """V1 API: Sends raw HTML"""
    url = f"{BASE_URL}/generate-sync"
    headers = {"Content-Type": "text/html; charset=utf-8"}
    return requests.post(url, data=html_content.encode("utf-8"), headers=headers, timeout=120)


def send_request_v2(html_content: str, bill_no: str, month: str) -> requests.Response:
    """V2 API: Sends JSON with bill_no and month"""
    url = f"{BASE_URL}/generate-sync-v2"
    headers = {"Content-Type": "application/json"}

    payload = {
        "html": html_content,
        "bill_no": bill_no,
        "month": month
    }

    return requests.post(url, json=payload, headers=headers, timeout=120)


# =========================================================
# 🔁 TOGGLE API HERE (COMMENT / UNCOMMENT)
# =========================================================
def send_request(html_content: str, bill_no: str = "", month: str = "") -> requests.Response:
    # 👉 USE V1
    # return send_request_v1(html_content)

    # 👉 USE V2 (uncomment below)
    return send_request_v2(html_content, bill_no, month)


# =========================================================
def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_bytes(data: bytes, filename: str, directory: Path) -> Path:
    ensure_dir(directory)
    file_path = directory / filename
    file_path.write_bytes(data)
    return file_path


def write_text(text: str, filename: str, directory: Path) -> Path:
    ensure_dir(directory)
    file_path = directory / filename
    file_path.write_text(text, encoding="utf-8")
    return file_path


# =========================================================
# ✅ SINGLE REQUEST
# =========================================================
def send_html_and_get_pdf(
    html_path: Path,
    output_dir: Path,
    bill_no: str,
    month: str,
) -> Path:

    if not html_path.is_file():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    ensure_dir(output_dir)

    html_content = html_path.read_text(encoding="utf-8")
    pdf_filename = f"{html_path.stem}.pdf"

    response = send_request(html_content, bill_no, month)

    if response.status_code != 200:
        raise RuntimeError(f"API Error {response.status_code}: {response.text[:300]}")

    if "pdf" not in response.headers.get("Content-Type", "").lower():
        write_bytes(response.content, f"{pdf_filename}.error", output_dir)
        raise RuntimeError("Response is not PDF")

    return write_bytes(response.content, pdf_filename, output_dir)


# =========================================================
# ✅ LOAD TEST WORKER
# =========================================================
def make_request_once(
    html_content: str,
    output_dir: Path,
    base_filename: str,
    index: int,
    save_pdf: bool,
    max_save: int,
    bill_no: str,
    month: str,
) -> Tuple[bool, float, Optional[str]]:

    start = time.perf_counter()

    try:
        response = send_request(html_content, bill_no, month)
        latency = time.perf_counter() - start

        if response.status_code != 200:
            return False, latency, f"HTTP {response.status_code}"

        if "pdf" not in response.headers.get("Content-Type", "").lower():
            return False, latency, "Invalid Content-Type"

        if save_pdf and (max_save == 0 or index < max_save):
            filename = f"{base_filename}_{index:05d}.pdf"
            write_bytes(response.content, filename, output_dir)

        return True, latency, None

    except Exception as e:
        latency = time.perf_counter() - start

        if save_pdf and (max_save == 0 or index < max_save):
            filename = f"{base_filename}_{index:05d}.error.txt"
            write_text(str(e), filename, output_dir)

        return False, latency, str(e)


# =========================================================
# ✅ LOAD TEST
# =========================================================
def run_load_test(
    html_path: Path,
    output_dir: Path,
    num_requests: int,
    concurrency: int,
    save_pdf: bool,
    max_save: int,
    bill_no: str,
    month: str,
):

    html_content = html_path.read_text(encoding="utf-8")
    base_filename = html_path.stem

    ensure_dir(output_dir)

    print("\n🚀 Starting Load Test...")
    print(f"Requests: {num_requests}, Concurrency: {concurrency}")

    start_time = time.perf_counter()

    success, failure = 0, 0
    latencies: List[float] = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(
                make_request_once,
                html_content,
                output_dir,
                base_filename,
                i,
                save_pdf,
                max_save,
                f"{bill_no}_{i}",  # unique bill_no per request
                month,
            )
            for i in range(num_requests)
        ]

        for fut in as_completed(futures):
            ok, latency, err = fut.result()
            latencies.append(latency)

            if ok:
                success += 1
            else:
                failure += 1

    total_time = time.perf_counter() - start_time

    print("\n===== RESULT =====")
    print(f"Total Requests : {num_requests}")
    print(f"Success        : {success}")
    print(f"Failed         : {failure}")
    print(f"RPS            : {num_requests / total_time:.2f}")
    print(f"Avg Latency    : {sum(latencies)/len(latencies)*1000:.2f} ms")


# =========================================================
def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--html-file", required=True)
    parser.add_argument("--output-dir", default="./pdf_output")

    parser.add_argument("--num-requests", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=10)

    parser.add_argument("--save-pdf", action="store_true")
    parser.add_argument("--max-save", type=int, default=0)

    # 👉 Required for V2 API
    parser.add_argument("--bill-no", default="TEST123")
    parser.add_argument("--month", default="2026-03")

    return parser.parse_args()


# =========================================================
def main():
    args = parse_args()

    html_path = Path(args.html_file)
    output_dir = Path(args.output_dir)

    # SINGLE REQUEST
    if args.num_requests <= 1:
        try:
            pdf_path = send_html_and_get_pdf(
                html_path,
                output_dir,
                args.bill_no,
                args.month
            )
            print(f"✅ PDF saved: {pdf_path}")
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)

    # LOAD TEST
    else:
        run_load_test(
            html_path,
            output_dir,
            args.num_requests,
            args.concurrency,
            args.save_pdf,
            args.max_save,
            args.bill_no,
            args.month
        )


# =========================================================
if __name__ == "__main__":
    main()