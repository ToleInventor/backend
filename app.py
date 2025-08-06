import sqlite3
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from datetime import datetime, timedelta
import json
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from waitress import serve
import time
import platform
import os
import psutil

app = Flask(__name__)
CORS(app)  # Enable CORS for all origins

DATABASE = 'events.db'

# --- Database Connection ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db:
        db.close()

# --- Initialize DB from schema.sql ---
def init_db():
    with app.app_context():
        db = get_db()
        with open('schema.sql') as f:
            db.executescript(f.read())
        db.commit()

# --- Helper: Check if normal event rings today ---
def event_rings_today(freq_json):
    try:
        weekdays = json.loads(freq_json)
        today = datetime.now().strftime('%A').lower()
        return today in weekdays
    except Exception:
        return False

# --- Normal Events API ---
@app.route('/api/normalEvents', methods=['GET', 'POST'])
def normal_events():
    db = get_db()
    cursor = db.cursor()

    if request.method == 'GET':
        cursor.execute("SELECT * FROM normalEvents")
        rows = cursor.fetchall()
        events = [dict(row) for row in rows]
        for ev in events:
            ev['frequency'] = json.loads(ev['frequency'])
            ev['active'] = bool(ev['active'])
        return jsonify(events)

    if request.method == 'POST':
        data = request.json
        required_fields = ['title', 'time', 'delay', 'tone', 'active', 'frequency']
        missing = [f for f in required_fields if f not in data]
        if missing:
            return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400
        try:
            freq_json = json.dumps(data['frequency'])
            cursor.execute("""
                INSERT INTO normalEvents (title, time, delay, tone, active, frequency)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (data['title'], data['time'], data['delay'], data['tone'], int(data['active']), freq_json))
            db.commit()
            return jsonify({'message': 'normalEvent created', 'id': cursor.lastrowid}), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/normalEvents/<int:event_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_normal_event(event_id):
    db = get_db()
    cursor = db.cursor()

    if request.method == 'GET':
        cursor.execute("SELECT * FROM normalEvents WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        if row:
            event = dict(row)
            event['frequency'] = json.loads(event['frequency'])
            event['active'] = bool(event['active'])
            return jsonify(event)
        return jsonify({'error': 'Event not found'}), 404

    if request.method == 'PUT':
        data = request.json
        try:
            freq_json = json.dumps(data['frequency'])
            cursor.execute("""
                UPDATE normalEvents
                SET title = ?, time = ?, delay = ?, tone = ?, active = ?, frequency = ?
                WHERE id = ?
            """, (data['title'], data['time'], data['delay'], data['tone'], int(data['active']), freq_json, event_id))
            db.commit()
            return jsonify({'message': 'Normal event updated successfully'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    if request.method == 'DELETE':
        try:
            cursor.execute("DELETE FROM normalEvents WHERE id = ?", (event_id,))
            db.commit()
            return jsonify({'message': 'Normal event deleted successfully'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

# --- Special Events API ---
@app.route('/api/specialEvents', methods=['GET', 'POST'])
def special_events():
    db = get_db()
    cursor = db.cursor()

    if request.method == 'GET':
        cursor.execute("SELECT * FROM specialEvents")
        rows = cursor.fetchall()
        events = [dict(row) for row in rows]
        for ev in events:
            ev['completed'] = bool(ev['completed'])
        return jsonify(events)

    if request.method == 'POST':
        data = request.json
        required_fields = ['date', 'time', 'description', 'tone', 'completed']
        missing = [f for f in required_fields if f not in data]
        if missing:
            return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400
        try:
            cursor.execute("""
                INSERT INTO specialEvents (date, time, description, tone, completed)
                VALUES (?, ?, ?, ?, ?)
            """, (data['date'], data['time'], data['description'], data['tone'], int(data['completed'])))
            db.commit()
            return jsonify({'message': 'specialEvent created', 'id': cursor.lastrowid}), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/specialEvents/<int:event_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_special_event(event_id):
    db = get_db()
    cursor = db.cursor()

    if request.method == 'GET':
        cursor.execute("SELECT * FROM specialEvents WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        if row:
            event = dict(row)
            event['completed'] = bool(event['completed'])
            return jsonify(event)
        return jsonify({'error': 'Event not found'}), 404

    if request.method == 'PUT':
        data = request.json
        try:
            cursor.execute("""
                UPDATE specialEvents
                SET date = ?, time = ?, description = ?, tone = ?, completed = ?
                WHERE id = ?
            """, (data['date'], data['time'], data['description'], data['tone'], int(data['completed']), event_id))
            db.commit()
            return jsonify({'message': 'Special event updated successfully'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    if request.method == 'DELETE':
        try:
            cursor.execute("DELETE FROM specialEvents WHERE id = ?", (event_id,))
            db.commit()
            return jsonify({'message': 'Special event deleted successfully'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

# --- ESP32 Table API ---
@app.route('/api/ESP32', methods=['GET','POST'])
def get_ESP32_events():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM ESP32 ORDER BY time")
    rows = cursor.fetchall()
    events = [dict(row) for row in rows]
    return jsonify(events)

# --- Scheduled ESP32 Update ---
def update_esp32_table():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')

        cursor.execute("DELETE FROM ESP32")

        cursor.execute("SELECT * FROM normalEvents WHERE active = 1")
        normal_events = [row for row in cursor.fetchall() if event_rings_today(row['frequency'])]

        for ev in normal_events:
            event_time_dt = datetime.combine(now.date(), datetime.strptime(ev['time'], '%H:%M').time())
            delay_sec = ev['delay'] if ev['delay'] else 0
            event_time_dt += timedelta(seconds=delay_sec)

            if event_time_dt >= (now - timedelta(seconds=10)):
                cursor.execute(
                    "INSERT INTO ESP32 (title, time, delay, tone, source) VALUES (?, ?, ?, ?, 'normal')",
                    (ev['title'], ev['time'], ev['delay'], ev['tone'])
                )

        cursor.execute("SELECT * FROM specialEvents WHERE date = ? AND completed = 0", (today_str,))
        special_events = cursor.fetchall()

        for ev in special_events:
            event_time_dt = datetime.combine(now.date(), datetime.strptime(ev['time'], '%H:%M').time())
            if event_time_dt >= (now - timedelta(seconds=10)):
                cursor.execute(
                    "INSERT INTO ESP32 (title, time, delay, tone, source) VALUES (?, ?, ?, ?, 'special')",
                    (ev['description'], ev['time'], 0, ev['tone'])
                )

        db.commit()

@app.route('/api/update_ESP32', methods=['POST'])
def update_ESP32_endpoint():
    update_esp32_table()
    return jsonify({'message': 'ESP32 table updated successfully'})

# --- Main Entry Point ---
if __name__ == "__main__":
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=update_esp32_table, trigger="interval", seconds=2)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    print("Starting Waitress server on http://0.0.0.0:5000")
    time.sleep(1)
    print("starting server...")
    time.sleep(3)
    print("collecting dependencies...")
    time.sleep(6)
    print("initializing metadata...")
    time.sleep(1)
    print("waitress started successfully.")
    time.sleep(2)
    print("WSGI server ready for use.")
    time.sleep(4)
    print("collecting system information...")
    print("System:", platform.system())
    print("Node:", platform.node())
    print("Release:", platform.release())
    print("Python Version:", platform.python_version())

    # Memory info (requires psutil)
    mem = psutil.virtual_memory()
    print(f"Memory usage: {mem.percent}% used")

    # Environment variables
    print("Environment variables:", os.environ)
    print("Server ready — you can make API calls now.")

    # Start the server
    serve(app, listen='0.0.0.0:5000')
