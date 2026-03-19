#!/usr/bin/env python3
r"""
Send an HTML file to a remote API that returns a PDF, then save the PDF locally.

Examples:

python api_testing.py --html-file templates/bill5_v9.html --output-dir pdf_output1 --num-requests 2 --concurrency 2 --save-pdf --max-save 2

python api_testing.py `
--html-file templates/bill5_v8_hindi.html `
--output-dir pdf_output1`
--num-requests 100 `
--concurrency 200 `
--save-pdf `
--max-save 10


python api_testing.py `
--html-file templates/bill5_v9.html `
--num-requests 10 `
--concurrency 10 `
--save-pdf `
--max-save 10 `
--local-save-path "D:\company_projects\test_pdfs"

Linux / mounted remote drive example:
python api_testing.py \
  --html-file templates/bill5_v9.html \
  --num-requests 10 \
  --concurrency 10 \
  --save-pdf \
  --max-save 10 \
  --local-save-path /data/test_pdfs \
  --remote-save-path /mnt/remote_pdf_share
"""

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, List
from datetime import datetime

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# BASE_URL = "http://10.98.7.221:8000"
BASE_URL = "https://pdfserv.mpwin.co.in"
# BASE_URL = "http://testing.mpwin.co.in/pdfbills"
PDF_ENDPOINT = "/generate-sync"
API_URL = f"{BASE_URL}{PDF_ENDPOINT}"
PAYLOAD_MODE = "raw_html"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_bytes_to_targets(
    data: bytes,
    filename: str,
    local_dir: Path,
    remote_dir: Optional[Path] = None,
) -> Path:
    """
    Save file in local_dir and optionally copy to remote_dir.
    Returns the local file path.
    """
    ensure_dir(local_dir)
    local_file = local_dir / filename
    local_file.write_bytes(data)

    if remote_dir:
        ensure_dir(remote_dir)
        remote_file = remote_dir / filename
        shutil.copy2(local_file, remote_file)

    return local_file


def write_text_to_targets(
    text: str,
    filename: str,
    local_dir: Path,
    remote_dir: Optional[Path] = None,
) -> Path:
    """
    Save text/debug file in local_dir and optionally copy to remote_dir.
    Returns the local file path.
    """
    ensure_dir(local_dir)
    local_file = local_dir / filename
    local_file.write_text(text, encoding="utf-8")

    if remote_dir:
        ensure_dir(remote_dir)
        remote_file = remote_dir / filename
        shutil.copy2(local_file, remote_file)

    return local_file


def send_html_and_get_pdf(
    html_path: Path,
    output_dir: Path,
    output_name: Optional[str] = None,
    remote_output_dir: Optional[Path] = None,
) -> Path:
    """Single-request helper: read HTML from file, call API, save PDF."""

    if not html_path.is_file():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    ensure_dir(output_dir)

    if output_name:
        pdf_filename = output_name if output_name.lower().endswith(".pdf") else f"{output_name}.pdf"
    else:
        pdf_filename = f"{html_path.stem}.pdf"

    # Read HTML
    html_content = html_path.read_text(encoding="utf-8")

    # Prepare request based on mode
    if PAYLOAD_MODE == "raw_html":
        headers = {"Content-Type": "text/html; charset=utf-8"}
        response = requests.post(API_URL, data=html_content.encode("utf-8"), headers=headers, timeout=120)
    elif PAYLOAD_MODE == "json_html":
        headers = {"Content-Type": "application/json"}
        payload = {"html": html_content}
        response = requests.post(API_URL, json=payload, headers=headers, timeout=120)
    else:
        raise ValueError(f"Unsupported PAYLOAD_MODE: {PAYLOAD_MODE}")

    # Check response
    if response.status_code != 200:
        raise RuntimeError(f"API returned status {response.status_code}: {response.text[:500]}")

    content_type = response.headers.get("Content-Type", "")
    if "pdf" not in content_type.lower():
        debug_name = f"{pdf_filename}.error-response"
        debug_path = write_bytes_to_targets(
            response.content,
            debug_name,
            output_dir,
            remote_output_dir,
        )
        raise RuntimeError(
            f"Expected PDF but got Content-Type '{content_type}'. "
            f"Saved raw response to: {debug_path}"
        )

    output_path = write_bytes_to_targets(
        response.content,
        pdf_filename,
        output_dir,
        remote_output_dir,
    )
    return output_path


def make_request_once(
    html_content: str,
    output_dir: Path,
    remote_output_dir: Optional[Path],
    base_filename: str,
    index: int,
    save_pdf: bool,
    max_save: int,
) -> Tuple[bool, float, Optional[str]]:
    """
    Worker for load test.
    Returns (success, latency_seconds, error_message_or_None).
    """

    t0 = time.perf_counter()
    try:
        if PAYLOAD_MODE == "raw_html":
            headers = {"Content-Type": "text/html; charset=utf-8"}
            response = requests.post(API_URL, data=html_content.encode("utf-8"), headers=headers, timeout=120)
        elif PAYLOAD_MODE == "json_html":
            headers = {"Content-Type": "application/json"}
            payload = {"html": html_content}
            response = requests.post(API_URL, json=payload, headers=headers, timeout=120)
        else:
            return False, 0.0, f"Unsupported PAYLOAD_MODE: {PAYLOAD_MODE}"

        latency = time.perf_counter() - t0

        if response.status_code != 200:
            if save_pdf and (max_save <= 0 or index < max_save):
                filename = f"{base_filename}_{index:05d}.error-response"
                write_bytes_to_targets(response.content, filename, output_dir, remote_output_dir)
            return False, latency, f"HTTP {response.status_code}"

        content_type = response.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower():
            if save_pdf and (max_save <= 0 or index < max_save):
                filename = f"{base_filename}_{index:05d}.error-response"
                write_bytes_to_targets(response.content, filename, output_dir, remote_output_dir)
            return False, latency, f"Unexpected Content-Type: {content_type}"

        if save_pdf and (max_save <= 0 or index < max_save):
            filename = f"{base_filename}_{index:05d}.pdf"
            write_bytes_to_targets(response.content, filename, output_dir, remote_output_dir)

        return True, latency, None

    except Exception as e:
        latency = time.perf_counter() - t0

        if save_pdf and (max_save <= 0 or index < max_save):
            filename = f"{base_filename}_{index:05d}.exception.txt"
            write_text_to_targets(str(e), filename, output_dir, remote_output_dir)

        return False, latency, str(e)


def run_load_test(
    html_path: Path,
    output_dir: Path,
    remote_output_dir: Optional[Path],
    num_requests: int,
    concurrency: int,
    save_pdf: bool,
    max_save: int,
) -> None:
    """Run a parallel load test against the API."""

    if not html_path.is_file():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    if num_requests <= 0:
        raise ValueError("num_requests must be > 0")

    if concurrency <= 0:
        raise ValueError("concurrency must be > 0")

    concurrency = min(concurrency, num_requests)

    html_content = html_path.read_text(encoding="utf-8")
    base_filename = html_path.stem

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / f"run_{timestamp}"
    remote_run_dir = (remote_output_dir / f"run_{timestamp}") if remote_output_dir else None

    if save_pdf:
        ensure_dir(run_dir)
        if remote_run_dir:
            ensure_dir(remote_run_dir)

    print("Starting load test:")
    print(f"  URL             : {API_URL}")
    print(f"  HTML file       : {html_path}")
    print(f"  Requests        : {num_requests}")
    print(f"  Concurrency     : {concurrency}")
    print(f"  Save PDFs       : {save_pdf}")
    print(f"  Max save        : {max_save if max_save > 0 else 'no limit'}")
    if save_pdf:
        print(f"  Local output    : {run_dir}")
        if remote_run_dir:
            print(f"  Remote output   : {remote_run_dir}")
    print("-" * 60)

    start_time = time.perf_counter()

    success_count = 0
    failure_count = 0
    latencies: List[float] = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        for i in range(num_requests):
            futures.append(
                executor.submit(
                    make_request_once,
                    html_content,
                    run_dir,
                    remote_run_dir,
                    base_filename,
                    i,
                    save_pdf,
                    max_save,
                )
            )

        for i, fut in enumerate(as_completed(futures), start=1):
            success, latency, error_msg = fut.result()
            latencies.append(latency)
            if success:
                success_count += 1
            else:
                failure_count += 1
                if failure_count <= 10:
                    print(f"[ERROR #{failure_count}] Request #{i}: {error_msg}", file=sys.stderr)

    total_time = time.perf_counter() - start_time

    latencies_sorted = sorted(latencies) if latencies else []
    avg_latency = sum(latencies_sorted) / len(latencies_sorted) if latencies_sorted else 0.0
    p95_index = max(0, int(0.95 * len(latencies_sorted)) - 1) if latencies_sorted else 0
    p95_latency = latencies_sorted[p95_index] if latencies_sorted else 0.0
    rps = num_requests / total_time if total_time > 0 else 0.0

    print("\nLoad test finished.")
    print("-" * 60)
    print(f"Total time          : {total_time:.2f} s")
    print(f"Total requests      : {num_requests}")
    print(f"Successful          : {success_count}")
    print(f"Failed              : {failure_count}")
    print(f"Requests per second : {rps:.2f} req/s")
    print(f"Average latency     : {avg_latency * 1000:.2f} ms")
    print(f"95th pct latency    : {p95_latency * 1000:.2f} ms")
    if save_pdf:
        print(f"Local files dir     : {run_dir}")
        if remote_run_dir:
            print(f"Remote files dir    : {remote_run_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send HTML to remote API and save returned PDF, with optional load testing."
    )
    parser.add_argument(
        "--html-file",
        required=True,
        help="Path to the input HTML file.",
    )
    parser.add_argument(
        "--output-dir",
        default="./pdf_output1",
        help="Directory where the PDF(s) will be saved if --local-save-path is not provided.",
    )
    parser.add_argument(
        "--local-save-path",
        default=None,
        help="Directory where PDFs/debug files will actually be saved. Overrides --output-dir.",
    )
    parser.add_argument(
        "--remote-save-path",
        default=None,
        help="Mounted remote directory / shared path where saved files will also be copied.",
    )
    parser.add_argument(
        "--filename",
        default=None,
        help="Output PDF filename (single-request mode). Default: <html-file-stem>.pdf",
    )
    parser.add_argument(
        "--num-requests",
        type=int,
        default=0,
        help="Total number of requests for load testing. If 0 or not set, only a single request is sent.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=50,
        help="Number of parallel requests for load testing (default: 50).",
    )
    parser.add_argument(
        "--save-pdf",
        action="store_true",
        help="In load test mode, save responses (PDF/error) to disk.",
    )
    parser.add_argument(
        "--max-save",
        type=int,
        default=0,
        help="Maximum number of responses to save in load test mode. 0 means no limit.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    html_path = Path(args.html_file).resolve()
    local_base_dir = Path(args.local_save_path).resolve() if args.local_save_path else Path(args.output_dir).resolve()
    remote_base_dir = Path(args.remote_save_path).resolve() if args.remote_save_path else None

    if args.num_requests and args.num_requests > 1:
        try:
            run_load_test(
                html_path=html_path,
                output_dir=local_base_dir,
                remote_output_dir=remote_base_dir,
                num_requests=args.num_requests,
                concurrency=args.concurrency,
                save_pdf=bool(args.save_pdf),
                max_save=int(args.max_save),
            )
        except Exception as e:
            print(f"[ERROR] Load test failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            pdf_path = send_html_and_get_pdf(
                html_path=html_path,
                output_dir=local_base_dir,
                output_name=args.filename,
                remote_output_dir=remote_base_dir,
            )
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

        print(f"[OK] PDF saved to: {pdf_path}")
        if remote_base_dir:
            print(f"[OK] PDF also copied to remote path: {remote_base_dir}")


if __name__ == "__main__":
    main()