import os
import sqlite3
import zipfile
import tarfile
import imghdr
from flask import Flask, request, render_template, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from PIL import Image, ExifTags
import pdfkit  # For PDF generation

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['EXTRACT_FOLDER'] = 'extracted'
app.config['ALLOWED_EXTENSIONS'] = {'db'}

# Create uploads and extract folders if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['EXTRACT_FOLDER'], exist_ok=True)

AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac'}

# PDF configuration
pdf_config = pdfkit.configuration(wkhtmltopdf='C:/Programs/wkhtmltopdf/bin/wkhtmltopdf.exe')  # Update path if needed


# Helper: Check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# Helper function: Extract zip or tar files
def extract_archive(filepath, extract_to):
    if filepath.endswith('.zip'):
        with zipfile.ZipFile(filepath, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
    elif filepath.endswith('.tar') or filepath.endswith('.tar.gz'):
        with tarfile.open(filepath, 'r') as tar_ref:
            tar_ref.extractall(extract_to)


# Helper function: Check if a file is an audio file based on its extension
def is_audio_file(filepath):
    file_extension = os.path.splitext(filepath)[1].lower()
    return file_extension in AUDIO_EXTENSIONS


# Helper function: Extract image creation date
def get_image_creation_date(filepath):
    try:
        with Image.open(filepath) as img:
            exif = img._getexif()
            if exif:
                for tag, value in exif.items():
                    tag_name = ExifTags.TAGS.get(tag)
                    if tag_name == 'DateTimeOriginal':
                        return value
    except Exception as e:
        print(f"Error reading EXIF data from {filepath}: {e}")
    return "Unknown"


# Helper function: Scan for image and audio files
def find_files(folder):
    image_data = []
    audio_paths = []
    for root, _, files in os.walk(folder):
        for file in files:
            file_path = os.path.join(root, file)
            if imghdr.what(file_path):  # Check if the file is an image
                creation_date = get_image_creation_date(file_path)
                image_data.append({"path": file_path, "creation_date": creation_date})
            elif is_audio_file(file_path):  # Check if the file is an audio
                audio_paths.append(file_path)
    return image_data, audio_paths


# Route: Home Page
@app.route('/')
def home():
    return render_template('index.html')


# Route: Upload Databases and Memory Dump
@app.route('/upload', methods=['POST'])
def upload_files():
    sms_file = request.files.get('sms_db')
    call_file = request.files.get('call_db')
    memory_dump = request.files.get('memory_dump')

    sms_filename = secure_filename(sms_file.filename) if sms_file and allowed_file(sms_file.filename) else None
    call_filename = secure_filename(call_file.filename) if call_file and allowed_file(call_file.filename) else None
    memory_filename = secure_filename(memory_dump.filename) if memory_dump else None

    if sms_file and sms_filename:
        sms_file.save(os.path.join(app.config['UPLOAD_FOLDER'], sms_filename))

    if call_file and call_filename:
        call_file.save(os.path.join(app.config['UPLOAD_FOLDER'], call_filename))

    if memory_dump and memory_filename:
        memory_dump.save(os.path.join(app.config['UPLOAD_FOLDER'], memory_filename))
        extract_archive(os.path.join(app.config['UPLOAD_FOLDER'], memory_filename), app.config['EXTRACT_FOLDER'])

    # Ensure at least one file is uploaded
    if not sms_filename and not call_filename and not memory_filename:
        return "No valid files uploaded", 400

    return redirect(url_for('analyze', sms_db=sms_filename, call_db=call_filename))

# Route: Analyze Databases
@app.route('/analyze')
def analyze():
    sms_filename = request.args.get('sms_db')
    call_filename = request.args.get('call_db')

    sms_results = extract_sms(os.path.join(app.config['UPLOAD_FOLDER'], sms_filename)) if sms_filename else []
    call_logs_results = extract_call_logs(os.path.join(app.config['UPLOAD_FOLDER'], call_filename)) if call_filename else []
    image_data, audio_paths = find_files(app.config['EXTRACT_FOLDER'])

    return render_template(
        'results.html',
        sms=sms_results,
        calls=call_logs_results,
        images=image_data,
        audio_paths=audio_paths,
        sms_db=sms_filename,
        call_db=call_filename
    )



# Function: Extract SMS from mmssms.db
def extract_sms(db_path):
    if not os.path.exists(db_path):
        return [{"error": "SMS database not found"}]
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT address, date, body FROM sms")
        messages = [{"address": row[0], "date": row[1], "body": row[2]} for row in cursor.fetchall()]
        conn.close()
        return messages
    except Exception as e:
        return [{"error": f"Error reading SMS database: {str(e)}"}]


# Function: Extract Call Logs from calllog.db
def extract_call_logs(db_path):
    if not os.path.exists(db_path):
        return [{"error": "Call log database not found"}]
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT number, date, duration, type FROM calls")
        calls = [{"number": row[0], "date": row[1], "duration": row[2], "type": row[3]} for row in cursor.fetchall()]
        conn.close()
        return calls
    except Exception as e:
        return [{"error": f"Error reading Call Logs database: {str(e)}"}]

# Route: Generate and Download PDF
@app.route('/download_pdf')
def download_pdf():
    sms_db = request.args.get('sms_db')
    call_db = request.args.get('call_db')

    # Handle missing files gracefully
    sms_results = extract_sms(os.path.join(app.config['UPLOAD_FOLDER'], sms_db)) if sms_db else []
    call_logs_results = extract_call_logs(os.path.join(app.config['UPLOAD_FOLDER'], call_db)) if call_db else []
    image_data, audio_paths = find_files(app.config['EXTRACT_FOLDER'])

    # Render the data into a PDF using a template
    rendered_html = render_template(
        'pdf_template.html',
        sms=sms_results,
        calls=call_logs_results,
        images=image_data,
        audio_paths=audio_paths
    )

    # Generate PDF from the rendered HTML
    pdf_path = 'analysis_report.pdf'
    pdfkit.from_string(rendered_html, pdf_path, configuration=pdf_config)

    return send_file(pdf_path, as_attachment=True, mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=True)
