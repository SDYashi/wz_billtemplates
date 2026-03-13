#!/usr/bin/env python3
"""
Send an HTML file to a remote API that returns a PDF, then save the PDF locally.

python api_testing.py --html-file templates/bill5_v9.html --output-dir pdf_output1 --num-requests 2 --concurrency 2 --save-pdf --max-save 2

python api_testing.py `
--html-file templates/bill5_v8_hindi.html `
--output-dir pdf_output `
--num-requests 100 `
--concurrency 200 `
--save-pdf `
--max-save 10

"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, List
from datetime import datetime

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://10.98.7.221:8000"
PDF_ENDPOINT = "/generate-sync"
API_URL = f"{BASE_URL}{PDF_ENDPOINT}"
PAYLOAD_MODE = "raw_html"

# ==================================================
def send_html_and_get_pdf(
    html_path: Path,
    output_dir: Path,
    output_name: Optional[str] = None,
) -> Path:
    """Single-request helper: read HTML from file, call API, save PDF."""

    if not html_path.is_file():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    if output_name:
        pdf_filename = output_name if output_name.lower().endswith(".pdf") else f"{output_name}.pdf"
    else:
        pdf_filename = f"{html_path.stem}.pdf"

    output_path = output_dir / pdf_filename

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
        raise RuntimeError(
            f"API returned status {response.status_code}: {response.text[:500]}"
        )

    content_type = response.headers.get("Content-Type", "")
    if "pdf" not in content_type.lower():
        # Still save it for debugging
        debug_path = output_dir / f"{pdf_filename}.error-response"
        debug_path.write_bytes(response.content)
        raise RuntimeError(
            f"Expected PDF but got Content-Type '{content_type}'. "
            f"Saved raw response to: {debug_path}"
        )

    # Save PDF
    output_path.write_bytes(response.content)
    return output_path

def make_request_once(
    html_content: str,
    output_dir: Path,
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
            # Optionally save some failures too (within max_save)
            if save_pdf and (max_save <= 0 or index < max_save):
                output_dir.mkdir(parents=True, exist_ok=True)
                debug_path = output_dir / f"{base_filename}_{index:05d}.error-response"
                debug_path.write_bytes(response.content)
            return False, latency, f"HTTP {response.status_code}"

        content_type = response.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower():
            if save_pdf and (max_save <= 0 or index < max_save):
                output_dir.mkdir(parents=True, exist_ok=True)
                debug_path = output_dir / f"{base_filename}_{index:05d}.error-response"
                debug_path.write_bytes(response.content)
            return False, latency, f"Unexpected Content-Type: {content_type}"

        if save_pdf and (max_save <= 0 or index < max_save):
            output_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = output_dir / f"{base_filename}_{index:05d}.pdf"
            pdf_path.write_bytes(response.content)

        return True, latency, None

    except Exception as e:
        latency = time.perf_counter() - t0

        # Optionally store exceptions as debug files too
        if save_pdf and (max_save <= 0 or index < max_save):
            output_dir.mkdir(parents=True, exist_ok=True)
            debug_path = output_dir / f"{base_filename}_{index:05d}.exception.txt"
            debug_path.write_text(str(e), encoding="utf-8")

        return False, latency, str(e)

def run_load_test(
    html_path: Path,
    output_dir: Path,
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

    # Load HTML once into memory
    html_content = html_path.read_text(encoding="utf-8")
    base_filename = html_path.stem

    # Create a timestamped run directory inside output_dir
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / f"run_{timestamp}"
    if save_pdf:
        run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Starting load test:")
    print(f"  URL          : {API_URL}")
    print(f"  HTML file    : {html_path}")
    print(f"  Requests     : {num_requests}")
    print(f"  Concurrency  : {concurrency}")
    print(f"  Save PDFs    : {save_pdf}")
    print(f"  Max save     : {max_save if max_save > 0 else 'no limit'}")
    if save_pdf:
        print(f"  Run output   : {run_dir}")
    print("-" * 60)

    start_time = time.perf_counter()

    success_count = 0
    failure_count = 0
    latencies: List[float] = []

    # Use ThreadPoolExecutor for parallel HTTP requests
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        for i in range(num_requests):
            futures.append(
                executor.submit(
                    make_request_once,
                    html_content,
                    run_dir,
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
                # Optional: print some errors (not all 10k)
                if failure_count <= 10:
                    print(f"[ERROR #{failure_count}] Request #{i}: {error_msg}", file=sys.stderr)

    total_time = time.perf_counter() - start_time

    # Basic stats
    latencies_sorted = sorted(latencies) if latencies else []
    avg_latency = sum(latencies_sorted) / len(latencies_sorted) if latencies_sorted else 0.0
    p95_latency = latencies_sorted[int(0.95 * len(latencies_sorted)) - 1] if latencies_sorted else 0.0
    rps = num_requests / total_time if total_time > 0 else 0.0

    print("\nLoad test finished.")
    print("-" * 60)
    print(f"Total time          : {total_time:.2f} s")
    print(f"Total requests      : {num_requests}")
    print(f"Successful          : {success_count}")
    print(f"Failed              : {failure_count}")
    print(f"Requests per second : {rps:.2f} req/s")
    print(f"Average latency     : {avg_latency*1000:.2f} ms")
    print(f"95th pct latency    : {p95_latency*1000:.2f} ms")
    if save_pdf:
        print(f"PDF/debug files dir : {run_dir}")

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
        default="./pdf_output",
        help="Directory where the PDF(s) will be saved (default: ./pdf_output).",
    )
    parser.add_argument(
        "--filename",
        default=None,
        help="Output PDF filename (single-request mode). Default: <html-file-stem>.pdf",
    )

    # Load test options
    parser.add_argument(
        "--num-requests",
        type=int,
        default=0,
        help="Total number of requests for load testing. "
             "If 0 or not set, only a single request is sent.",
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
        help="Maximum number of responses to save in load test mode. "
             "0 means no limit (save all when --save-pdf is used).",
    )

    return parser.parse_args()

def main() -> None:
    args = parse_args()
    html_path = Path(args.html_file).resolve()
    output_dir = Path(args.output_dir).resolve()

    # Load test mode
    if args.num_requests and args.num_requests > 1:
        try:
            run_load_test(
                html_path=html_path,
                output_dir=output_dir,
                num_requests=args.num_requests,
                concurrency=args.concurrency,
                save_pdf=bool(args.save_pdf),
                max_save=int(args.max_save),
            )
        except Exception as e:
            print(f"[ERROR] Load test failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Single-request mode (original behavior)
        try:
            pdf_path = send_html_and_get_pdf(html_path, output_dir, args.filename)
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)
        print(f"[OK] PDF saved to: {pdf_path}")

if __name__ == "__main__":
    main()
