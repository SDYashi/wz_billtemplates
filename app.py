from flask import Flask, abort, render_template, jsonify
import json
from pathlib import Path
import subprocess
import os
from flask import jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename

BASE_DIR = r"D:\company_projects\flask_projects\pdfgenerator"
PDF_ROOT = os.path.join(BASE_DIR, "pdf_output1")
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

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/pdf/<folder>/<filename>")
def serve_pdf(folder, filename):
    safe_folder = secure_filename(folder)
    safe_filename = secure_filename(filename)

    folder_path = os.path.join(PDF_ROOT, safe_folder)

    if not os.path.isdir(folder_path):
        abort(404, description="Folder not found")

    file_path = os.path.join(folder_path, safe_filename)
    if not os.path.isfile(file_path):
        abort(404, description="File not found")

    return send_from_directory(folder_path, safe_filename)


@app.route("/WZ_VIEW_PDFS", methods=["GET"])
def view_pdfs_api():
    result = []

    if not os.path.exists(PDF_ROOT):
        return jsonify([]), 200

    for folder in os.scandir(PDF_ROOT):
        if folder.is_dir():
            pdf_files = [
                file.name
                for file in os.scandir(folder.path)
                if file.is_file() and file.name.lower().endswith(".pdf")
            ]

            result.append({
                "folder": folder.name,
                "files": sorted(pdf_files)
            })

    result.sort(key=lambda x: x["folder"], reverse=True)
    return jsonify(result), 200

@app.route("/view_pdfs_page")
def view_pdfs_page():
    return render_template("view_pdfs.html")

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
        "--num-requests", "2",
        "--concurrency", "2",
        "--save-pdf",
        "--max-save", "2"
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