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
HTML_FILE = "bill.html"
NUM_REQUESTS = 10000        # Total requests
MAX_WORKERS = 20           # Parallel threads

# ------------------------------
# Function to run one request
# ------------------------------
def _run_one(session: requests.Session, i: int, html_content: str) -> dict:
    start_time = time.perf_counter()
    try:
        response = session.post(
            URL,
            json={"html": html_content},
        )
        end_time = time.perf_counter()
        latency_ms = round((end_time - start_time) * 1000, 2)

        if response.status_code == 200:
            with open(f"{output_dir}/response_{i}.pdf", "wb") as file:
                file.write(response.content)
            return {"success": True, "latency": latency_ms}
        else:
            print(f"Error {i}: {response.status_code}")
            return {"success": False, "latency": latency_ms}
    except Exception as e:
        end_time = time.perf_counter()
        latency_ms = round((end_time - start_time) * 1000, 2)
        print(f"Exception {i}: {e}")
        return {"success": False, "latency": latency_ms}

# ------------------------------
# Load test function
# ------------------------------
def generate_load_test(num_requests: int = NUM_REQUESTS, max_workers: int = MAX_WORKERS) -> None:
    # Load HTML content
    with open(HTML_FILE, "r", encoding="utf-8") as file:
        html_content = file.read()

    results = []
    start_time = time.perf_counter()

    # Using a single session shared across threads
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

    # ------------------------------
    # Summary statistics
    # ------------------------------
    total_requests = len(results)
    successful = sum(1 for r in results if r["success"])
    failed = total_requests - successful
    avg_latency = round(mean(r["latency"] for r in results), 2)
    requests_per_sec = round(total_requests / total_time, 2)
    latencies_sorted = sorted(r["latency"] for r in results)
    pct_95_latency = round(latencies_sorted[int(0.95 * total_requests) - 1], 2)

    # ------------------------------
    # Print summary
    # ------------------------------
    print("\nLoad test finished.")
    print("-" * 60)
    print(f"Total time          : {total_time} s")
    print(f"Total requests      : {total_requests}")
    print(f"Successful          : {successful}")
    print(f"Failed              : {failed}")
    print(f"Requests per second : {requests_per_sec} req/s")
    print(f"Average latency     : {avg_latency} ms")
    print(f"95th pct latency    : {pct_95_latency} ms")
    print(f"Local files dir     : {os.path.abspath(output_dir)}")

# ------------------------------
# Run script
# ------------------------------
if __name__ == "__main__":
    generate_load_test()