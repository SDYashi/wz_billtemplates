from flask import Flask, render_template, jsonify
import json
from pathlib import Path
import subprocess
import os

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
JSON_FILE_EN = BASE_DIR / "bill_data_english.json"
JSON_FILE_HI = BASE_DIR / "bill_data_hindi.json"


def load_bill_data_en():
    with open(JSON_FILE_EN, "r", encoding="utf-8") as f:
        return json.load(f)

def load_bill_data_hi():
    with open(JSON_FILE_HI, "r", encoding="utf-8") as f:
        return json.load(f)
  

@app.route("/WZ_BILL_ENGLISH_JSON")
def bill_view_en_json():

    # Step 1: Load JSON data
    data = load_bill_data_en()
    
    # Step 2: Render HTML with JSON data
    rendered_html = render_template("bill5_v9_json.html", **data)

    # Step 3: Save rendered HTML to file
    output_html = "generated_bill.html"
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(rendered_html)

    # Step 4: Call Python script
    subprocess.Popen([
        "python",
        "api_testing.py",
        "--html-file", output_html,
        "--output-dir", "pdf_output1",
        "--num-requests", "100000",
        "--concurrency", "200",
        "--save-pdf",
        "--max-save", "100000"
    ])

    return {"message": "Bill generated successfully. Check pdf_output1 folder"}

@app.route("/WZ_BILL_HINDI_JSON")
def bill_view_hi_json():

    # Step 1: Load JSON data
    data = load_bill_data_hi()

    # Step 2: Render HTML with JSON data
    rendered_html = render_template("bill5_v9_hindi_json.html", **data)

    # Step 3: Save rendered HTML to file
    output_html = "generated_bill.html"
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(rendered_html)

    # Step 4: Call Python script
    subprocess.Popen([
        "python",
        "api_testing.py",
        "--html-file", output_html,
        "--output-dir", "pdf_output1",
        "--num-requests", "2",
        "--concurrency", "2",
        "--save-pdf",
        "--max-save", "2"
    ])

    return {"message": "Bill generated successfully. Check pdf_output1 folder"}

@app.route("/WZ_BILL_HINDI")
def bill_view_hi():
    subprocess.Popen([
        "python",
        "api_testing.py",
        "--html-file", "templates/bill5_v9_hindi.html",
        "--output-dir", "pdf_output1",
        "--num-requests", "2",
        "--concurrency", "2",
        "--save-pdf",
        "--max-save", "2"
    ])
    return {"message": "bIll generated successfully in hindi check pdf_output1 folder"}

@app.route("/WZ_BILL_ENGLISH")
def bill_view_en():
    subprocess.Popen([
        "python",
        "api_testing.py",
        "--html-file", "templates/bill5_v9.html",
        "--output-dir", "pdf_output1",
        "--num-requests", "2",
        "--concurrency", "2",
        "--save-pdf",
        "--max-save", "2"
    ])
    return {"message": "bIll generated successfully in english check pdf_output1 folder"}


if __name__ == "__main__":
    app.run(debug=True , host="0.0.0.0", port=5000, use_reloader=False)