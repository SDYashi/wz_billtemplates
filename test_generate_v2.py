import requests
from pathlib import Path

# 🔧 CONFIG
BASE_URL = "http://testing.mpwin.co.in/pdfbills"
ENDPOINT = "/generate-sync-v2"
API_URL = f"{BASE_URL}{ENDPOINT}"

HTML_FILE = "templates/bill5_v10.html"
OUTPUT_PDF = "output.pdf"

BILL_NO = "TEST123"
MONTH = "March"

def main():
    html_path = Path(HTML_FILE)

    if not html_path.exists():
        print(f"❌ HTML file not found: {HTML_FILE}")
        return

    html_content = html_path.read_text(encoding="utf-8")

    headers = {
        "Content-Type": "text/html",
        "bill_no": BILL_NO,
        "month": MONTH
    }

    print(f"🚀 Calling API: {API_URL}")

    try:
        response = requests.post(
            API_URL,
            data=html_content.encode("utf-8"),
            headers=headers,
            timeout=120
        )
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return

    print(f"Status Code: {response.status_code}")

    if response.status_code != 200:
        print("❌ Error Response:")
        print(response.text[:500])
        return

    content_type = response.headers.get("Content-Type", "")

    if "pdf" not in content_type.lower():
        print(f"❌ Expected PDF but got: {content_type}")
        print(response.text[:500])
        return

    # ✅ Save PDF
    with open(OUTPUT_PDF, "wb") as f:
        f.write(response.content)

    print(f"✅ PDF saved as: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()