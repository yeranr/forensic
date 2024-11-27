import os
import sqlite3
from flask import Flask, request, render_template, redirect, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'db'}

# Create uploads folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Helper: Check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Route: Home Page
@app.route('/')
def home():
    return render_template('index.html')

# Route: Upload Databases
@app.route('/upload', methods=['POST'])
def upload_files():
    sms_file = request.files.get('sms_db')
    call_file = request.files.get('call_db')

    # Validate files
    if sms_file and allowed_file(sms_file.filename):
        sms_filename = secure_filename(sms_file.filename)
        sms_path = os.path.join(app.config['UPLOAD_FOLDER'], sms_filename)
        sms_file.save(sms_path)
    else:
        sms_path = None

    if call_file and allowed_file(call_file.filename):
        call_filename = secure_filename(call_file.filename)
        call_path = os.path.join(app.config['UPLOAD_FOLDER'], call_filename)
        call_file.save(call_path)
    else:
        call_path = None

    # Ensure at least one file is provided
    if not sms_path and not call_path:
        return "No valid files uploaded", 400

    return redirect(url_for('analyze', sms_db=sms_filename if sms_path else '', call_db=call_filename if call_path else ''))

# Route: Analyze Databases
@app.route('/analyze')
def analyze():
    sms_filename = request.args.get('sms_db')
    call_filename = request.args.get('call_db')

    sms_results = extract_sms(os.path.join(app.config['UPLOAD_FOLDER'], sms_filename)) if sms_filename else []
    call_logs_results = extract_call_logs(os.path.join(app.config['UPLOAD_FOLDER'], call_filename)) if call_filename else []

    return render_template('results.html', sms=sms_results, calls=call_logs_results)

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

# Function: Extract Call Logs from contacts2.db
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

if __name__ == '__main__':
    app.run(debug=True)
