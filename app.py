from flask import Flask, render_template, request, send_file, session, redirect, url_for, flash
from werkzeug.utils import secure_filename
from pathlib import Path
from collections import Counter, defaultdict
import os, re, csv, io, json, uuid, statistics

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'syllabussync-local-demo-change-me')
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / 'uploads'
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {'pdf'}
MAX_MB = 25
app.config['MAX_CONTENT_LENGTH'] = MAX_MB * 1024 * 1024

# Sentence Transformers is preferred. If it cannot be loaded, TF-IDF provides a
# transparent local fallback so the prototype remains usable without an API.
_model = None
_model_attempted = False
_model_error = None
_RESULTS = {}


def get_model():
    global _model, _model_attempted, _model_error

    # Use lightweight TF-IDF on the cloud unless explicitly enabled.
    use_transformer = os.environ.get(
        "USE_SENTENCE_TRANSFORMERS", "0"
    ).strip().lower() in {"1", "true", "yes"}

    if not use_transformer:
        return None

    if _model_attempted:
        return _model

    _model_attempted = True
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(
            os.environ.get("SENTENCE_MODEL", "all-MiniLM-L6-v2")
        )
    except Exception as exc:
        _model_error = str(exc)
        _model = None

    return _model


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def clean_text(text):
    text = text.replace('\x00', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip(' \t\n\r•▪◦-–—:;,.')


def extract_pdf(path):
    if fitz is None:
        raise RuntimeError('PyMuPDF is not installed. Run: pip install -r requirements.txt')
    pages = []
    with fitz.open(path) as doc:
        if doc.is_encrypted:
            raise ValueError('This PDF is password-protected. Please upload an unlocked PDF.')
        for index, page in enumerate(doc):
            raw_text = page.get_text('text').replace('\x00', ' ').replace('\r', '\n')
            text = re.sub(r'[ \t]+', ' ', raw_text)
            text = re.sub(r'\n{3,}', '\n\n', text).strip()
            pages.append({'page': index + 1, 'text': text})
    full = '\n'.join(p['text'] for p in pages if p['text'])
    if len(full.strip()) < 25:
        raise ValueError('Almost no selectable text was found. This version supports text-based PDFs; scanned PDFs need OCR.')
    return pages


def split_sentences(text):
    # Keep bullets/headings useful while splitting long paragraphs into searchable units.
    chunks = []
    for raw in re.split(r'\n+|(?<=[.!?])\s+(?=[A-Z0-9])', text):
        item = clean_text(raw)
        if len(item) >= 8:
            if len(item) > 420:
                chunks.extend(clean_text(x) for x in re.split(r'[,;:]\s+', item) if len(clean_text(x)) >= 8)
            else:
                chunks.append(item)
    return chunks


def syllabus_topics(pages):
    topics = []
    skip = re.compile(r'^(unit\s*[-:]*\s*\d*|module\s*[-:]*\s*\d*|chapter\s*\d*|contents?|index|syllabus|course outcomes?|objectives?|references?|text books?|credits?|lecture|tutorial|practical|total marks|duration|semester|b\.tech|bachelor of|department of)', re.I)
    for page in pages:
        raw_lines = page['text'].replace('•', '\n').replace('▪', '\n').replace('◦', '\n')
        for raw in re.split(r'\n+', raw_lines):
            line = clean_text(raw)
            line = re.sub(r'^(?:\d+(?:\.\d+)*[.)]?|[a-z][.)])\s+', '', line, flags=re.I)
            if len(line) < 8 or len(line) > 260 or skip.match(line):
                continue
            # Avoid treating page furniture and administrative text as topics.
            words = re.findall(r"[A-Za-z][A-Za-z+'-]*", line)
            if len(words) < 2 or len(words) > 38:
                continue
            if not any(ch.isalpha() for ch in line):
                continue
            topics.append({'topic': line, 'page': page['page']})
    # De-duplicate lightly while preserving first source page.
    unique = []
    seen = set()
    for item in topics:
        key = re.sub(r'[^a-z0-9]+', ' ', item['topic'].lower()).strip()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:250]


def build_passages(pages, label):
    passages = []
    for page in pages:
        for chunk in split_sentences(page['text']):
            passages.append({'text': chunk, 'page': page['page'], 'source': label})
    return passages


def similarity_matrix(left_texts, right_texts):
    model = get_model()
    if model is not None:
        import numpy as np
        left = model.encode(left_texts, normalize_embeddings=True, show_progress_bar=False)
        right = model.encode(right_texts, normalize_embeddings=True, show_progress_bar=False)
        return np.matmul(left, right.T), 'Sentence Transformers (all-MiniLM-L6-v2)'
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words='english', sublinear_tf=True)
    all_texts = left_texts + right_texts
    matrix = vectorizer.fit_transform(all_texts)
    return cosine_similarity(matrix[:len(left_texts)], matrix[len(left_texts):]), 'TF-IDF fallback (install/download Sentence Transformers for semantic matching)'


def analyze(syllabus_pages, notes_pages, pyq_pages):
    topics = syllabus_topics(syllabus_pages)
    if not topics:
        raise ValueError('Could not detect syllabus topics. Use a text-based syllabus PDF with clear topic lines or bullets.')
    note_passages = build_passages(notes_pages, 'Study notes')
    pyq_passages = build_passages(pyq_pages, 'Previous-year papers')
    if not note_passages:
        raise ValueError('No usable text found in the notes PDF.')
    scores, method = similarity_matrix([t['topic'] for t in topics], [p['text'] for p in note_passages])
    coverage = []
    for i, topic in enumerate(topics):
        order = sorted(range(len(note_passages)), key=lambda j: float(scores[i][j]), reverse=True)[:3]
        best = float(scores[i][order[0]]) if order else 0.0
        # Semantic similarity is evidence of related content, not proof of full explanation.
        if best >= 0.62:
            status = 'Covered'
        elif best >= 0.40:
            status = 'Partially Covered'
        elif best >= 0.28:
            status = 'Needs Review'
        else:
            status = 'Missing'
        evidence = []
        for j in order:
            score = float(scores[i][j])
            if score >= 0.20:
                evidence.append({'text': note_passages[j]['text'][:360], 'page': note_passages[j]['page'], 'score': round(score * 100, 1)})
        coverage.append({
            'topic': topic['topic'], 'syllabus_page': topic['page'], 'status': status,
            'similarity': round(best * 100, 1), 'evidence': evidence,
            'priority': 'High' if status == 'Missing' else ('Medium' if status in ('Partially Covered', 'Needs Review') else 'Low')
        })

    # Match PYQ passages to syllabus topics. Year is inferred only when explicitly visible in the source text.
    pyq_matrix, pyq_method = similarity_matrix([t['topic'] for t in topics], [p['text'] for p in pyq_passages]) if pyq_passages else ([], method)
    pyq_rows = []
    topic_counts = Counter()
    year_counts = defaultdict(Counter)
    for j, passage in enumerate(pyq_passages):
        if not topics:
            continue
        if len(pyq_passages):
            best_i = max(range(len(topics)), key=lambda i: float(pyq_matrix[i][j]))
            score = float(pyq_matrix[best_i][j])
            if score >= 0.28:
                year_match = re.search(r'\b(20(?:0\d|1\d|2\d))\b', passage['text'])
                year = year_match.group(1) if year_match else 'Year not identified'
                topic_name = topics[best_i]['topic']
                topic_counts[topic_name] += 1
                year_counts[topic_name][year] += 1
                pyq_rows.append({'question': passage['text'][:300], 'page': passage['page'], 'topic': topic_name, 'similarity': round(score * 100, 1), 'year': year})
    pyq_rows.sort(key=lambda r: (r['page'], -r['similarity']))
    for item in coverage:
        item['pyq_count'] = topic_counts[item['topic']]
        item['years'] = dict(year_counts[item['topic']])
    counts = Counter(item['status'] for item in coverage)
    total = len(coverage)
    covered_pct = round(counts['Covered'] / total * 100) if total else 0
    return {
        'coverage': coverage, 'pyq_rows': pyq_rows, 'counts': dict(counts), 'total_topics': total,
        'covered_pct': covered_pct, 'pyq_matched': len(pyq_rows), 'method': method,
        'pyq_method': pyq_method, 'syllabus_pages': len(syllabus_pages), 'notes_pages': len(notes_pages), 'pyq_pages': len(pyq_pages),
        'warning': 'Automated matches can be wrong. Similarity is not proof of complete coverage; review evidence before relying on it.',
    }


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze_route():
    fields = [('syllabus', 'Official syllabus'), ('notes', 'Study notes'), ('pyq', 'Previous-year question papers')]
    paths = {}
    try:
        for key, label in fields:
            file = request.files.get(key)
            if not file or not file.filename:
                raise ValueError(f'Please upload the {label} PDF.')
            if not allowed_file(file.filename):
                raise ValueError(f'{label}: only PDF files are accepted.')
            path = UPLOAD_DIR / f'{uuid.uuid4().hex}_{secure_filename(file.filename)}'
            file.save(path)
            paths[key] = path
        pages = {key: extract_pdf(path) for key, path in paths.items()}
        result = analyze(pages['syllabus'], pages['notes'], pages['pyq'])
        result['filenames'] = {key: paths[key].name.split('_', 1)[-1] for key, _ in fields}
        result_id = uuid.uuid4().hex
        _RESULTS[result_id] = result
        session['result_id'] = result_id
        session.modified = True
        return render_template('results.html', result=result)
    except Exception as exc:
        flash(str(exc), 'error')
        return redirect(url_for('index'))
    finally:
        for path in paths.values():
            try: path.unlink(missing_ok=True)
            except Exception: pass


@app.route('/download/csv')
def download_csv():
    result = _RESULTS.get(session.get('result_id'))
    if not result:
        flash('Run an analysis first.', 'error'); return redirect(url_for('index'))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Syllabus topic', 'Syllabus page', 'Coverage status', 'Best similarity (%)', 'Priority', 'PYQ count', 'Evidence pages', 'Best evidence'])
    for item in result['coverage']:
        evidence = item.get('evidence', [])
        writer.writerow([item['topic'], item['syllabus_page'], item['status'], item['similarity'], item['priority'], item['pyq_count'], ', '.join(str(e['page']) for e in evidence), evidence[0]['text'] if evidence else 'No matching evidence found'])
    output.seek(0)
    return send_file(io.BytesIO(('\ufeff' + output.getvalue()).encode('utf-8')), mimetype='text/csv', as_attachment=True, download_name='syllabussync_analysis.csv')


@app.route('/download/report')
def download_report():
    result = _RESULTS.get(session.get('result_id'))
    if not result:
        flash('Run an analysis first.', 'error'); return redirect(url_for('index'))
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        from reportlab.lib.units import mm
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=12*mm, leftMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='SmallCell', parent=styles['BodyText'], fontSize=7, leading=9, alignment=TA_LEFT, wordWrap='CJK'))
        story = [Paragraph('SyllabusSync AI — Syllabus Gap Analysis', styles['Title']), Spacer(1, 5*mm)]
        story.append(Paragraph(f"Topics detected: {result['total_topics']} &nbsp;&nbsp; | &nbsp;&nbsp; Fully covered: {result['covered_pct']}% &nbsp;&nbsp; | &nbsp;&nbsp; PYQ matches: {result['pyq_matched']}", styles['BodyText']))
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph('Coverage breakdown', styles['Heading2']))
        data = [[Paragraph('<b>Topic</b>', styles['SmallCell']), Paragraph('<b>Status</b>', styles['SmallCell']), Paragraph('<b>Similarity</b>', styles['SmallCell']), Paragraph('<b>Priority</b>', styles['SmallCell']), Paragraph('<b>PYQ count</b>', styles['SmallCell']), Paragraph('<b>Evidence (page)</b>', styles['SmallCell'])]]
        for item in result['coverage']:
            ev = item['evidence'][0] if item['evidence'] else None
            evidence_text = (f"p. {ev['page']}: {ev['text'][:140]}" if ev else 'No matching evidence found')
            data.append([Paragraph(item['topic'][:180], styles['SmallCell']), Paragraph(item['status'], styles['SmallCell']), Paragraph(f"{item['similarity']}%", styles['SmallCell']), Paragraph(item['priority'], styles['SmallCell']), Paragraph(str(item['pyq_count']), styles['SmallCell']), Paragraph(evidence_text, styles['SmallCell'])])
        table = Table(data, colWidths=[58*mm, 30*mm, 20*mm, 20*mm, 20*mm, 105*mm], repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#142a43')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#d8e0e8')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f7fa')]),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.append(table)
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph('Important note', styles['Heading2']))
        story.append(Paragraph(result['warning'], styles['BodyText']))
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(f"Matching method: {result['method']}. PYQ matching method: {result['pyq_method']}.", styles['BodyText']))
        doc.build(story)
        buffer.seek(0)
        return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name='syllabussync_analysis_report.pdf')
    except ImportError:
        flash('PDF export needs ReportLab. Run: pip install reportlab', 'error')
        return redirect(url_for('results_page'))


@app.route('/results')
def results_page():
    result = _RESULTS.get(session.get('result_id'))
    if not result:
        return redirect(url_for('index'))
    return render_template('results.html', result=result)


@app.errorhandler(413)
def too_large(_error):
    flash(f'Each request must stay under {MAX_MB} MB total. Try smaller PDFs.', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
