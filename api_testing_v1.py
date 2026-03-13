#!/usr/bin/env python3
"""
Send an HTML file to a remote API that returns a PDF, then save the PDF locally.

Examples:

python api_testing.py --html-file templates/bill5_v9.html --output-dir pdf_output1 --num-requests 2 --concurrency 2 --save-pdf --max-save 2

python api_testing.py --html-file templates/bill5_v9.html --output-dir pdf_output1 --page-size A4 --margin-top 5mm --margin-bottom 5mm --margin-left 5mm --margin-right 5mm --zoom 0.90

python api_testing.py --html-file templates/bill5_v9.html --output-dir pdf_output1 --payload-mode json_html --page-size A4 --zoom 0.85 --save-pdf --max-save 2
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://10.98.7.221:8000"
PDF_ENDPOINT = "/generate-sync"
API_URL = f"{BASE_URL}{PDF_ENDPOINT}"
DEFAULT_PAYLOAD_MODE = "raw_html"  # raw_html or json_html


def build_pdf_options(args: argparse.Namespace) -> Dict[str, Any]:
    """Build PDF/wkhtmltopdf-style options from CLI args."""
    options: Dict[str, Any] = {}

    if args.page_size:
        options["page-size"] = args.page_size
    if args.page_width:
        options["page-width"] = args.page_width
    if args.page_height:
        options["page-height"] = args.page_height

    if args.margin_top:
        options["margin-top"] = args.margin_top
    if args.margin_bottom:
        options["margin-bottom"] = args.margin_bottom
    if args.margin_left:
        options["margin-left"] = args.margin_left
    if args.margin_right:
        options["margin-right"] = args.margin_right

    if args.zoom is not None:
        options["zoom"] = str(args.zoom)

    if args.dpi is not None:
        options["dpi"] = str(args.dpi)

    if args.orientation:
        options["orientation"] = args.orientation

    if args.grayscale:
        options["grayscale"] = True

    if args.lowquality:
        options["lowquality"] = True

    if args.disable_smart_shrinking:
        options["disable-smart-shrinking"] = True

    if args.print_media_type:
        options["print-media-type"] = True

    options["encoding"] = "UTF-8"
    return options


def build_headers(pdf_options: Dict[str, Any]) -> Dict[str, str]:
    """
    Put PDF options into HTTP headers for raw_html mode.
    Backend must read these headers.
    """
    headers = {
        "Content-Type": "text/html; charset=utf-8",
        "X-Page-Size": str(pdf_options.get("page-size", "")),
        "X-Page-Width": str(pdf_options.get("page-width", "")),
        "X-Page-Height": str(pdf_options.get("page-height", "")),
        "X-Margin-Top": str(pdf_options.get("margin-top", "")),
        "X-Margin-Bottom": str(pdf_options.get("margin-bottom", "")),
        "X-Margin-Left": str(pdf_options.get("margin-left", "")),
        "X-Margin-Right": str(pdf_options.get("margin-right", "")),
        "X-Zoom": str(pdf_options.get("zoom", "")),
        "X-DPI": str(pdf_options.get("dpi", "")),
        "X-Orientation": str(pdf_options.get("orientation", "")),
        "X-Grayscale": str(pdf_options.get("grayscale", False)).lower(),
        "X-Lowquality": str(pdf_options.get("lowquality", False)).lower(),
        "X-Disable-Smart-Shrinking": str(pdf_options.get("disable-smart-shrinking", False)).lower(),
        "X-Print-Media-Type": str(pdf_options.get("print-media-type", False)).lower(),
        "X-Encoding": str(pdf_options.get("encoding", "UTF-8")),
    }
    return headers


def send_request(html_content: str, payload_mode: str, pdf_options: Dict[str, Any], timeout: int = 120) -> requests.Response:
    """Send request according to payload mode."""
    if payload_mode == "raw_html":
        headers = build_headers(pdf_options)
        return requests.post(API_URL, data=html_content.encode("utf-8"), headers=headers, timeout=timeout)

    if payload_mode == "json_html":
        headers = {"Content-Type": "application/json"}
        payload = {
            "html": html_content,
            "options": pdf_options,
        }
        return requests.post(API_URL, json=payload, headers=headers, timeout=timeout)

    raise ValueError(f"Unsupported payload mode: {payload_mode}")


def send_html_and_get_pdf(
    html_path: Path,
    output_dir: Path,
    output_name: Optional[str],
    payload_mode: str,
    pdf_options: Dict[str, Any],
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
    html_content = html_path.read_text(encoding="utf-8")

    response = send_request(html_content, payload_mode, pdf_options)

    if response.status_code != 200:
        raise RuntimeError(f"API returned status {response.status_code}: {response.text[:500]}")

    content_type = response.headers.get("Content-Type", "")
    if "pdf" not in content_type.lower():
        debug_path = output_dir / f"{pdf_filename}.error-response"
        debug_path.write_bytes(response.content)
        raise RuntimeError(
            f"Expected PDF but got Content-Type '{content_type}'. Saved raw response to: {debug_path}"
        )

    output_path.write_bytes(response.content)
    return output_path


def make_request_once(
    html_content: str,
    output_dir: Path,
    base_filename: str,
    index: int,
    save_pdf: bool,
    max_save: int,
    payload_mode: str,
    pdf_options: Dict[str, Any],
) -> Tuple[bool, float, Optional[str]]:
    """Worker for load test. Returns (success, latency_seconds, error_message_or_None)."""

    t0 = time.perf_counter()
    try:
        response = send_request(html_content, payload_mode, pdf_options)
        latency = time.perf_counter() - t0

        if response.status_code != 200:
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
    payload_mode: str,
    pdf_options: Dict[str, Any],
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
    if save_pdf:
        run_dir.mkdir(parents=True, exist_ok=True)

    print("Starting load test:")
    print(f"  URL          : {API_URL}")
    print(f"  HTML file    : {html_path}")
    print(f"  Requests     : {num_requests}")
    print(f"  Concurrency  : {concurrency}")
    print(f"  Payload mode : {payload_mode}")
    print(f"  PDF options  : {json.dumps(pdf_options, ensure_ascii=False)}")
    print(f"  Save PDFs    : {save_pdf}")
    print(f"  Max save     : {max_save if max_save > 0 else 'no limit'}")
    if save_pdf:
        print(f"  Run output   : {run_dir}")
    print("-" * 60)

    start_time = time.perf_counter()
    success_count = 0
    failure_count = 0
    latencies: List[float] = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(
                make_request_once,
                html_content,
                run_dir,
                base_filename,
                i,
                save_pdf,
                max_save,
                payload_mode,
                pdf_options,
            )
            for i in range(num_requests)
        ]

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
        print(f"PDF/debug files dir : {run_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send HTML to remote API and save returned PDF, with optional load testing."
    )

    parser.add_argument("--html-file", required=True, help="Path to the input HTML file.")
    parser.add_argument("--output-dir", default="./pdf_output", help="Directory for saved PDF(s).")
    parser.add_argument("--filename", default=None, help="Output PDF filename in single-request mode.")
    parser.add_argument(
        "--payload-mode",
        default=DEFAULT_PAYLOAD_MODE,
        choices=["raw_html", "json_html"],
        help="How to send HTML/options to API.",
    )

    parser.add_argument("--num-requests", type=int, default=0, help="Total requests for load testing.")
    parser.add_argument("--concurrency", type=int, default=50, help="Parallel requests for load testing.")
    parser.add_argument("--save-pdf", action="store_true", help="Save responses in load test mode.")
    parser.add_argument("--max-save", type=int, default=0, help="Max responses to save. 0 means no limit.")

    # PDF/page options
    parser.add_argument("--page-size", default="A4", help="A4, A5, Letter, Legal, etc.")
    parser.add_argument("--page-width", default=None, help="Custom page width like 210mm")
    parser.add_argument("--page-height", default=None, help="Custom page height like 297mm")
    parser.add_argument("--margin-top", default="5mm", help="Top margin")
    parser.add_argument("--margin-bottom", default="5mm", help="Bottom margin")
    parser.add_argument("--margin-left", default="5mm", help="Left margin")
    parser.add_argument("--margin-right", default="5mm", help="Right margin")
    parser.add_argument("--zoom", type=float, default=0.90, help="Zoom factor like 0.90")
    parser.add_argument("--dpi", type=int, default=96, help="DPI")
    parser.add_argument("--orientation", choices=["Portrait", "Landscape"], default="Portrait")
    parser.add_argument("--grayscale", action="store_true", help="Render grayscale PDF")
    parser.add_argument("--lowquality", action="store_true", help="Enable lowquality mode")
    parser.add_argument("--disable-smart-shrinking", action="store_true", help="Disable smart shrinking")
    parser.add_argument("--print-media-type", action="store_true", help="Use print media type CSS")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    html_path = Path(args.html_file).resolve()
    output_dir = Path(args.output_dir).resolve()
    pdf_options = build_pdf_options(args)

    if args.num_requests and args.num_requests > 1:
        try:
            run_load_test(
                html_path=html_path,
                output_dir=output_dir,
                num_requests=args.num_requests,
                concurrency=args.concurrency,
                save_pdf=bool(args.save_pdf),
                max_save=int(args.max_save),
                payload_mode=args.payload_mode,
                pdf_options=pdf_options,
            )
        except Exception as e:
            print(f"[ERROR] Load test failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            pdf_path = send_html_and_get_pdf(
                html_path=html_path,
                output_dir=output_dir,
                output_name=args.filename,
                payload_mode=args.payload_mode,
                pdf_options=pdf_options,
            )
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)
        print(f"[OK] PDF saved to: {pdf_path}")


if __name__ == "__main__":
    main()