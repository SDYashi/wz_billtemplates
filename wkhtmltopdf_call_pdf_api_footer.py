#!/usr/bin/env python3

# python wkhtmltopdf_call_pdf_api_footer.py --html-file templates/bill5_v10.html --api-mode footer --bill-no BILL1001 --month "March 2026"


import argparse
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, List

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://testing.mpwin.co.in/pdfbills"


# =========================================================
# API FUNCTIONS
# =========================================================
def send_request_no_footer(html_content: str) -> requests.Response:
    """
    API without footer
    Endpoint:
        POST /generate-sync
    Payload:
        {
            "html": "<html>...</html>"
        }
    """
    url = f"{BASE_URL}/generate-sync"
    headers = {"Content-Type": "application/json"}
    payload = {
        "html": html_content
    }
    return requests.post(url, json=payload, headers=headers, timeout=120)


def send_request_with_footer(
    html_content: str,
    bill_no: str,
    month: str,
) -> requests.Response:
    """
    API with footer
    Endpoint:
        POST /generate-sync-ebill
    Payload:
        {
            "html": "<html>...</html>",
            "bill_no": "BILL-1001",
            "month": "March 2026"
        }
    """
    url = f"{BASE_URL}/generate-sync-ebill"
    headers = {"Content-Type": "application/json"}
    payload = {
        "html": html_content,
        "bill_no": bill_no,
        "month": month
    }
    return requests.post(url, json=payload, headers=headers, timeout=120)


def send_request(
    html_content: str,
    api_mode: str,
    bill_no: str = "",
    month: str = "",
) -> requests.Response:
    """
    Select which API to call based on api_mode
    api_mode:
        - no-footer
        - footer
    """
    if api_mode == "no-footer":
        return send_request_no_footer(html_content)

    if api_mode == "footer":
        return send_request_with_footer(html_content, bill_no, month)

    raise ValueError(f"Invalid api_mode: {api_mode}")


# =========================================================
# FILE HELPERS
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
# SINGLE REQUEST
# =========================================================
def send_html_and_get_pdf(
    html_path: Path,
    output_dir: Path,
    api_mode: str,
    bill_no: str,
    month: str,
) -> Path:
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    ensure_dir(output_dir)

    html_content = html_path.read_text(encoding="utf-8")
    suffix = "with_footer" if api_mode == "footer" else "no_footer"
    pdf_filename = f"{html_path.stem}_{suffix}.pdf"

    response = send_request(
        html_content=html_content,
        api_mode=api_mode,
        bill_no=bill_no,
        month=month,
    )

    if response.status_code != 200:
        raise RuntimeError(f"API Error {response.status_code}: {response.text[:500]}")

    content_type = response.headers.get("Content-Type", "").lower()
    if "pdf" not in content_type:
        write_bytes(response.content, f"{pdf_filename}.error.bin", output_dir)
        raise RuntimeError(f"Response is not PDF. Content-Type: {content_type}")

    return write_bytes(response.content, pdf_filename, output_dir)


# =========================================================
# LOAD TEST WORKER
# =========================================================
def make_request_once(
    html_content: str,
    output_dir: Path,
    base_filename: str,
    index: int,
    save_pdf: bool,
    max_save: int,
    api_mode: str,
    bill_no: str,
    month: str,
) -> Tuple[bool, float, Optional[str]]:
    start = time.perf_counter()

    try:
        current_bill_no = bill_no
        if api_mode == "footer":
            current_bill_no = f"{bill_no}_{index}"

        response = send_request(
            html_content=html_content,
            api_mode=api_mode,
            bill_no=current_bill_no,
            month=month,
        )

        latency = time.perf_counter() - start

        if response.status_code != 200:
            return False, latency, f"HTTP {response.status_code}: {response.text[:300]}"

        content_type = response.headers.get("Content-Type", "").lower()
        if "pdf" not in content_type:
            return False, latency, f"Invalid Content-Type: {content_type}"

        if save_pdf and (max_save == 0 or index < max_save):
            suffix = "with_footer" if api_mode == "footer" else "no_footer"
            filename = f"{base_filename}_{suffix}_{index:05d}.pdf"
            write_bytes(response.content, filename, output_dir)

        return True, latency, None

    except Exception as e:
        latency = time.perf_counter() - start

        if save_pdf and (max_save == 0 or index < max_save):
            suffix = "with_footer" if api_mode == "footer" else "no_footer"
            filename = f"{base_filename}_{suffix}_{index:05d}.error.txt"
            write_text(str(e), filename, output_dir)

        return False, latency, str(e)


# =========================================================
# LOAD TEST
# =========================================================
def run_load_test(
    html_path: Path,
    output_dir: Path,
    num_requests: int,
    concurrency: int,
    save_pdf: bool,
    max_save: int,
    api_mode: str,
    bill_no: str,
    month: str,
) -> None:
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    html_content = html_path.read_text(encoding="utf-8")
    base_filename = html_path.stem

    ensure_dir(output_dir)

    print("\n=========================================================")
    print("Starting Load Test")
    print("=========================================================")
    print(f"API Mode    : {api_mode}")
    print(f"Requests    : {num_requests}")
    print(f"Concurrency : {concurrency}")
    print(f"Save PDF    : {save_pdf}")
    print(f"Max Save    : {max_save}")
    print("=========================================================")

    start_time = time.perf_counter()

    success = 0
    failure = 0
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
                api_mode,
                bill_no,
                month,
            )
            for i in range(num_requests)
        ]

        for i, fut in enumerate(as_completed(futures), start=1):
            ok, latency, err = fut.result()
            latencies.append(latency)

            if ok:
                success += 1
            else:
                failure += 1
                print(f"[FAILED] Request {i}: {err}")

    total_time = time.perf_counter() - start_time
    avg_latency_ms = (sum(latencies) / len(latencies) * 1000) if latencies else 0.0
    min_latency_ms = (min(latencies) * 1000) if latencies else 0.0
    max_latency_ms = (max(latencies) * 1000) if latencies else 0.0
    rps = (num_requests / total_time) if total_time > 0 else 0.0

    print("\n=========================================================")
    print("RESULT")
    print("=========================================================")
    print(f"API Mode       : {api_mode}")
    print(f"Total Requests : {num_requests}")
    print(f"Success        : {success}")
    print(f"Failed         : {failure}")
    print(f"Total Time     : {total_time:.2f} sec")
    print(f"RPS            : {rps:.2f}")
    print(f"Avg Latency    : {avg_latency_ms:.2f} ms")
    print(f"Min Latency    : {min_latency_ms:.2f} ms")
    print(f"Max Latency    : {max_latency_ms:.2f} ms")
    print("=========================================================")


# =========================================================
# ARGUMENTS
# =========================================================
def parse_args():
    parser = argparse.ArgumentParser(
        description="Call HTML to PDF APIs with or without footer"
    )

    parser.add_argument(
        "--html-file",
        required=True,
        help="Path to input HTML file"
    )

    parser.add_argument(
        "--output-dir",
        default="./pdf_output",
        help="Directory to save PDFs/errors"
    )

    parser.add_argument(
        "--api-mode",
        choices=["no-footer", "footer"],
        default="no-footer",
        help="Choose API mode: no-footer or footer"
    )

    parser.add_argument(
        "--num-requests",
        type=int,
        default=0,
        help="Number of requests. 0 or 1 = single request, >1 = load test"
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of parallel workers for load test"
    )

    parser.add_argument(
        "--save-pdf",
        action="store_true",
        help="Save returned PDFs during load test"
    )

    parser.add_argument(
        "--max-save",
        type=int,
        default=0,
        help="Maximum PDFs to save during load test. 0 = save all"
    )

    parser.add_argument(
        "--bill-no",
        default="TEST123",
        help="Bill number used only for footer API"
    )

    parser.add_argument(
        "--month",
        default="2026-03",
        help="Month used only for footer API"
    )

    return parser.parse_args()


# =========================================================
# MAIN
# =========================================================
def main():
    args = parse_args()

    html_path = Path(args.html_file)
    output_dir = Path(args.output_dir)

    if args.num_requests <= 1:
        try:
            pdf_path = send_html_and_get_pdf(
                html_path=html_path,
                output_dir=output_dir,
                api_mode=args.api_mode,
                bill_no=args.bill_no,
                month=args.month,
            )
            print(f"PDF saved successfully: {pdf_path}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        try:
            run_load_test(
                html_path=html_path,
                output_dir=output_dir,
                num_requests=args.num_requests,
                concurrency=args.concurrency,
                save_pdf=args.save_pdf,
                max_save=args.max_save,
                api_mode=args.api_mode,
                bill_no=args.bill_no,
                month=args.month,
            )
        except Exception as e:
            print(f"Load test error: {e}")
            sys.exit(1)


# =========================================================
if __name__ == "__main__":
    main()