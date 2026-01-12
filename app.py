import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = "secure_production_core_2026"
socketio = SocketIO(app, cors_allowed_origins="*")
UPLOAD_FOLDER = 'static/uploads'

# --- Database Logic ---
def get_db():
    return sqlite3.connect('transmission_system.db')

def init_db():
    with get_db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS users (role TEXT PRIMARY KEY, password TEXT)')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            conn.execute("INSERT INTO users VALUES ('sender', 'sender123')")
            conn.execute("INSERT INTO users VALUES ('receiver', 'receiver123')")
            conn.execute("INSERT INTO users VALUES ('admin', 'admin123')")
        conn.commit()

# --- Utility Functions ---
def get_storage_stats():
    total_size = 0
    if os.path.exists(UPLOAD_FOLDER):
        for f in os.listdir(UPLOAD_FOLDER):
            fp = os.path.join(UPLOAD_FOLDER, f)
            if os.path.isfile(fp):
                total_size += os.path.getsize(fp)
    used_mb = round(total_size / (1024 * 1024), 2)
    percent = min((used_mb / 500) * 100, 100)
    return used_mb, percent

# --- Socket Monitoring ---
@socketio.on('connect')
def handle_connect():
    role = session.get('role', 'Unknown')
    socketio.emit('log_activity', {'msg': f'Node [{role}] joined the network.'})

@socketio.on('disconnect')
def handle_disconnect():
    role = session.get('role', 'Unknown')
    socketio.emit('log_activity', {'msg': f'Node [{role}] disconnected.'})

# --- Routes ---
@app.route('/')
def index():
    return render_template('login.html', error=request.args.get('error'))

@app.route('/auth', methods=['POST'])
def auth():
    role, password = request.form.get('role'), request.form.get('password')
    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE role=? AND password=?', (role, password)).fetchone()
    if user:
        session['role'] = role
        return redirect(url_for(role))
    return redirect(url_for('index', error='true'))

@app.route('/sender')
def sender():
    if session.get('role') != 'sender': return redirect('/')
    return render_template('sender.html', success=request.args.get('success'))

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if file and file.filename != '':
        filename = "".join([c for c in file.filename if c.isalnum() or c in ('.', '_')]).strip()
        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)
        socketio.emit('notify_receiver', {'filename': filename})
        socketio.emit('log_activity', {'msg': f'Sender transmitted file: {filename}'})
        return redirect(url_for('sender', success='true'))
    return redirect(url_for('sender'))

@app.route('/receiver')
def receiver():
    if session.get('role') != 'receiver': return redirect('/')
    files = os.listdir(UPLOAD_FOLDER)
    return render_template('receiver.html', files=files)

@app.route('/admin')
def admin():
    if session.get('role') != 'admin': return redirect('/')
    files = os.listdir(UPLOAD_FOLDER)
    used_mb, percent = get_storage_stats()
    return render_template('admin.html', files=files, used_mb=used_mb, percent=percent,
                           updated=request.args.get('updated'), deleted=request.args.get('deleted'))

@app.route('/update_pw', methods=['POST'])
def update_pw():
    role, new_pw = request.form.get('target_role'), request.form.get('new_password')
    with get_db() as conn:
        conn.execute('UPDATE users SET password=? WHERE role=?', (new_pw, role))
    socketio.emit('log_activity', {'msg': f'Admin changed password for {role}.'})
    return redirect(url_for('admin', updated='true'))

@app.route('/delete/<filename>')
def delete_file(filename):
    if session.get('role') == 'admin':
        path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(path): os.remove(path)
        socketio.emit('log_activity', {'msg': f'Admin deleted file: {filename}'})
    return redirect(url_for('admin', deleted='true'))

if __name__ == '__main__':
    init_db()
    if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)
    socketio.run(app, host='0.0.0.0', port=5000)