import os
import time
import tempfile
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from jd_analyzer import analyze_job_description
from resume_analyzer import analyze_resume
from app import extract_text_from_pdf, extract_text_from_docx

load_dotenv()

# --------------------------
# GOOGLE SHEETS AUTH SETUP
# --------------------------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1SlJtRj4HnSxrpGUqzR-pmGOvfL5v8hirNzQMR9LwIJE/edit")
worksheet = sheet.get_worksheet(0)

# --------------------------
# STEP 1: GET JD & ANALYZE
# --------------------------
print("Paste your Job Description (End with a blank line):")
jd_lines = []
while True:
    line = input()
    if not line.strip():
        break
    jd_lines.append(line)

job_description = "\n".join(jd_lines).strip()

if not job_description:
    print("[❌] No JD entered. Exiting.")
    exit()

print("\n[🔍] Analyzing JD via OpenAI...")
requirements = analyze_job_description(job_description)
if not requirements:
    print("[❌] JD analysis failed.")
    exit()
print("[✅] JD requirements extracted.\n")

# --------------------------
# DOWNLOAD AND EXTRACT UTILS
# --------------------------
def download_gdrive_file(link):
    """Download file from public Google Drive share link."""
    if "id=" in link:
        file_id = link.split("id=")[-1]
    elif "/d/" in link:
        file_id = link.split("/d/")[1].split("/")[0]
    else:
        raise ValueError("Invalid Google Drive URL format.")
    
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    r = requests.get(url)
    if r.status_code != 200:
        raise Exception("Download failed.")
    
    ext = ".pdf" if "pdf" in r.headers.get("Content-Type", "") else ".docx"
    path = tempfile.mktemp(suffix=ext)
    with open(path, "wb") as f:
        f.write(r.content)
    return path

def extract_text(path):
    if path.endswith(".pdf"):
        return extract_text_from_pdf(open(path, "rb"))
    elif path.endswith(".docx"):
        return extract_text_from_docx(open(path, "rb"))
    else:
        raise ValueError("Unsupported format for text extraction.")

# --------------------------
# MAIN LOOP: ROW PROCESSING
# --------------------------
rows = worksheet.get_all_records()
for i, row in enumerate(rows, start=2):  # Row 2 onward (header is row 1)
    link = row.get("Resume", "").strip()
    if not link:
        continue

    print(f"🔄 Processing Row {i}...")

    try:
        path = download_gdrive_file(link)
        resume_text = extract_text(path)
        result = analyze_resume(resume_text, requirements)
        
        if not result:
            worksheet.update_cell(i, len(row)+1, "Analysis failed")
            continue
        
        score = result["score"]
        recommendation = result["analysis"]["final_recommendation"]
        summary = result["analysis"]["qualitative_assessment"].get("recruiter_style_summary", "N/A")
        
        # Write results to next empty columns
        existing_row_len = len(worksheet.row_values(i))
        worksheet.update_cell(i, existing_row_len + 1, score)
        worksheet.update_cell(i, existing_row_len + 2, recommendation)
        worksheet.update_cell(i, existing_row_len + 3, summary)

        print(f"[✅] Row {i} done: {score} | {recommendation}")

    except Exception as e:
        print(f"[❌] Row {i} failed: {e}")
        worksheet.update_cell(i, len(row)+1, f"Error: {str(e)}")
    
    time.sleep(1.5)  # Respectful delay to avoid API abuse

print("\n🎉 Done analyzing all resumes.")
