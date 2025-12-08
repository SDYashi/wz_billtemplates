
import os
import json
from flask import Flask, render_template, send_file, request, abort, jsonify, make_response
import pdfkit
from io import BytesIO

app = Flask(__name__)

# Configure wkhtmltopdf (set env var WKHTMLTOPDF_PATH on Windows if needed)
WKHTMLTOPDF_PATH = os.environ.get("WKHTMLTOPDF_PATH")  # e.g. r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"

if WKHTMLTOPDF_PATH:
    pdf_config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)
else:
    pdf_config = None  # assume wkhtmltopdf is in PATH

pdf_options = {
    "page-size": "A4",
    "margin-top": "8mm",
    "margin-right": "8mm",
    "margin-bottom": "8mm",
    "margin-left": "8mm",
    "encoding": "UTF-8",
}

VALID_CATEGORIES = {
    "domestic": "bill_domestic.html",
    "nondomestic": "bill_nondomestic.html",
    "industrial": "bill_industrial.html",
    "agriculture": "bill_agriculture.html",
}


def load_sample_data(category: str) -> dict:
    data_file = os.path.join(os.path.dirname(__file__), "sample_data", f"{category}.json")
    if not os.path.exists(data_file):
        raise FileNotFoundError(f"Sample data not found for {category}")
    with open(data_file, "r", encoding="utf-8") as f:
        return json.load(f)


def render_bill_html(category: str, data: dict) -> str:
    template_name = VALID_CATEGORIES.get(category)
    if not template_name:
        abort(404, description="Unknown category")
    return render_template(template_name, data=data, category=category)


def html_to_pdf_bytes(html: str) -> bytes:
    pdf_bytes = pdfkit.from_string(html, False, options=pdf_options, configuration=pdf_config)
    return pdf_bytes


@app.route("/")
def index():
    return jsonify({
        "message": "Power Bill PDF API",
        "categories": list(VALID_CATEGORIES.keys()),
        "routes": {
            "preview": "/bill/<category>/view",
            "pdf": "/bill/<category>/pdf",
            "api": "/api/generate-bill",
        },
        "example_api_body": {
            "category": "domestic",
            "data": "optional custom bill data; if omitted default sample is used"
        }
    })


@app.route("/bill/<category>/view")
def view_bill(category):
    category = category.lower()
    if category not in VALID_CATEGORIES:
        abort(404, "Unknown category")
    data = load_sample_data(category)
    html = render_bill_html(category, data)
    return html


@app.route("/bill/<category>/pdf")
def bill_pdf(category):
    category = category.lower()
    if category not in VALID_CATEGORIES:
        abort(404, "Unknown category")
    data = load_sample_data(category)
    html = render_bill_html(category, data)
    pdf_bytes = html_to_pdf_bytes(html)
    filename = f"{category}_bill_sample.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@app.post("/api/generate-bill")
def api_generate_bill():
    """
    POST JSON:
    {
        "category": "domestic" | "nondomestic" | "industrial" | "agriculture",
        "data": {...}   # optional custom bill JSON matching template keys
    }
    """
    payload = request.get_json(silent=True) or {}
    category = (payload.get("category") or "").lower()
    if category not in VALID_CATEGORIES:
        return jsonify({"error": "Invalid or missing 'category'"}), 400

    if isinstance(payload.get("data"), dict):
        data = payload["data"]
    else:
        data = load_sample_data(category)

    html = render_bill_html(category, data)
    pdf_bytes = html_to_pdf_bytes(html)

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename=\"{category}_bill.pdf\"'
    return response


if __name__ == "__main__":
    app.run(debug=True)
