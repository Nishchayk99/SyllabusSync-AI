# SyllabusSync AI — Mini Project

A local Flask web application based on the submitted mini-project synopsis. Upload exactly three text-based PDFs: official syllabus, study notes, and previous-year question papers (PYQs). It extracts page-level text, matches syllabus topics to notes, classifies coverage, shows evidence snippets/page numbers, analyses topic occurrences in PYQs, and exports CSV/PDF reports.

## Stack
- Frontend: HTML5, CSS3, JavaScript
- Backend: Python + Flask
- PDF extraction: PyMuPDF
- Preferred matching: Sentence Transformers (`all-MiniLM-L6-v2`)
- Local fallback: TF-IDF with scikit-learn (not semantic AI; labelled in the results)
- Export: CSV and ReportLab PDF

## Run on Windows 10/11
1. Install Python 3.10 or newer from https://www.python.org/downloads/ and enable **Add Python to PATH**.
2. Extract this folder to a location such as `C:\SyllabusSyncAI`.
3. Double-click `run_windows.bat`, or open a terminal in the folder and run:
   ```powershell
   py -3 -m venv .venv
   .venv\Scripts\activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   python app.py
   ```
4. On first launch, the sentence-embedding model may download from the internet (several hundred MB). Wait for it to finish.
5. Open http://127.0.0.1:5000 in your browser.

## How to use
- Upload an official syllabus PDF, notes PDF, and PYQ PDF in their matching slots.
- Select **Analyse PDFs** and wait for extraction/matching.
- Review the dashboard, status labels, similarity scores, page-linked evidence, PYQ topic matches, and frequency counts.
- Download the CSV or PDF report.

## Important limitations
- This prototype is intended for English-language, text-based PDFs. Scanned/image-only PDFs need OCR, which is a future enhancement described in the synopsis.
- Topic extraction is heuristic; syllabus layouts vary, so inspect the detected topic list and evidence.
- Similarity thresholds are configurable in `app.py`. A similarity score does not prove a topic is fully taught or completely missing. Human review is required.
- PYQ frequency is historical only, not a prediction of future exam questions. Year-wise analysis works only when a year is identifiable in the question text.
- This is a local student prototype, not a production service. Do not expose it to the public internet without adding authentication, CSRF protections, stronger file isolation, and deployment hardening.
- No paid AI API is used. The preferred model runs locally after its initial download. If it cannot be loaded, the app clearly labels the TF-IDF fallback.

## Project structure
```
app.py
requirements.txt
run_windows.bat
README.md
templates/
  index.html
  results.html
static/
  styles.css
  app.js
```
