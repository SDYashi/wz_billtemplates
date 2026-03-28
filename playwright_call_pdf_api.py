import os
import time
import requests
from statistics import mean
from concurrent.futures import ThreadPoolExecutor, as_completed

# ------------------------------
# Configuration
# ------------------------------
output_dir = "output"
os.makedirs(output_dir, exist_ok=True)

URL = "http://testing.mpwin.co.in/playwright/generate_pdf"
HTML_FILE = "templates/bill5_v10.html"

NUM_REQUESTS = 100

MAX_WORKERS = 5

# Footer config
SHOW_FOOTER = True
BILL_NO = "123456789"
MONTH = "March 2026"

# Optional PDF config
FORMAT = "A4"
PRINT_BACKGROUND = True
PREFER_CSS_PAGE_SIZE = True
LANDSCAPE = False
MARGIN_TOP = "5mm"
MARGIN_BOTTOM = "5mm"
MARGIN_LEFT = "5mm"
MARGIN_RIGHT = "5mm"

# ------------------------------
# Function to run one request
# ------------------------------
def _run_one(session: requests.Session, i: int, html_content: str) -> dict:
    start_time = time.perf_counter()

    payload = {
        "html": html_content,
        "show_footer": SHOW_FOOTER,
        "bill_no": f"{BILL_NO}-{i}",   # unique bill no per request
        "month": MONTH,
        "format": FORMAT,
        "print_background": PRINT_BACKGROUND,
        "prefer_css_page_size": PREFER_CSS_PAGE_SIZE,
        "landscape": LANDSCAPE,
        "margin_top": MARGIN_TOP,
        "margin_bottom": MARGIN_BOTTOM,
        "margin_left": MARGIN_LEFT,
        "margin_right": MARGIN_RIGHT,
    }

    try:
        response = session.post(URL, json=payload, timeout=120)
        end_time = time.perf_counter()
        latency_ms = round((end_time - start_time) * 1000, 2)

        if response.status_code == 200:
            with open(f"{output_dir}/response_{i}.pdf", "wb") as file:
                file.write(response.content)
            return {
                "success": True,
                "latency": latency_ms,
                "status_code": response.status_code,
            }
        else:
            print(f"Error {i}: {response.status_code} - {response.text[:300]}")
            return {
                "success": False,
                "latency": latency_ms,
                "status_code": response.status_code,
            }

    except Exception as e:
        end_time = time.perf_counter()
        latency_ms = round((end_time - start_time) * 1000, 2)
        print(f"Exception {i}: {e}")
        return {
            "success": False,
            "latency": latency_ms,
            "status_code": None,
        }

# ------------------------------
# Load test function
# ------------------------------
def generate_load_test(num_requests: int = NUM_REQUESTS, max_workers: int = MAX_WORKERS) -> None:
    with open(HTML_FILE, "r", encoding="utf-8") as file:
        html_content = file.read()

    results = []
    start_time = time.perf_counter()

    with requests.Session() as session:
        session.trust_env = False

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(_run_one, session, i + 1, html_content)
                for i in range(num_requests)
            ]

            for f in as_completed(futures):
                results.append(f.result())

    end_time = time.perf_counter()
    total_time = round(end_time - start_time, 2)

    total_requests = len(results)
    successful = sum(1 for r in results if r["success"])
    failed = total_requests - successful

    latencies = [r["latency"] for r in results]
    avg_latency = round(mean(latencies), 2) if latencies else 0
    requests_per_sec = round(total_requests / total_time, 2) if total_time > 0 else 0

    latencies_sorted = sorted(latencies)
    pct_95_latency = round(latencies_sorted[int(0.95 * total_requests) - 1], 2) if total_requests else 0

    print("\nLoad test finished.")
    print("-" * 60)
    print(f"Total time          : {total_time} s")
    print(f"Total requests      : {total_requests}")
    print(f"Successful          : {successful}")
    print(f"Failed              : {failed}")
    print(f"Requests per second : {requests_per_sec} req/s")
    print(f"Average latency     : {avg_latency} ms")
    print(f"95th pct latency    : {pct_95_latency} ms")
    print(f"Footer enabled      : {SHOW_FOOTER}")
    print(f"Local files dir     : {os.path.abspath(output_dir)}")

# ------------------------------
# Run script
# ------------------------------
if __name__ == "__main__":
    generate_load_test()