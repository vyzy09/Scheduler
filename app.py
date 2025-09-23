import sqlite3
from flask import Flask, render_template, request, redirect, session, url_for, g, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "scheduler.db")

app = Flask(__name__)
app.secret_key = "replace_this_with_a_strong_secret_in_prod"  # CHANGE for production
app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://username:password@localhost/scheduler_db"

print("Database path:", DB_PATH)  # Added print statement to show the database path

# ---------- DB helpers ----------
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        date TEXT,
        time TEXT,
        notes TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # Add Venue table
    c.execute("""
    CREATE TABLE IF NOT EXISTS venue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        location TEXT NOT NULL
    )
    """)
    db.commit()
    db.close()

# ---------- Auth helpers ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            print("Redirecting to login: user not in session")  # Debug print
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def get_user_by_username(username):
    db = get_db()
    cur = db.execute("SELECT * FROM users WHERE username = ?", (username,))
    return cur.fetchone()

def get_user_by_id(uid):
    db = get_db()
    cur = db.execute("SELECT * FROM users WHERE id = ?", (uid,))
    return cur.fetchone()

# ---------- Routes ----------
@app.route("/")
@login_required
def index():
    db = get_db()
    cur = db.execute("SELECT * FROM schedule WHERE user_id = ? ORDER BY date, time", (session["user_id"],))
    tasks = cur.fetchall()
    user = get_user_by_id(session["user_id"])
    venues_cur = db.execute("SELECT * FROM venue ORDER BY name")
    venues = venues_cur.fetchall()
    return render_template("index.html", tasks=tasks, user=user, venues=venues)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if not username or not password:
            flash("Username and password required.")
            return redirect(url_for("register"))
        if get_user_by_username(username):
            flash("Username already taken.")
            return redirect(url_for("register"))
        pw_hash = generate_password_hash(password)
        db = get_db()
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pw_hash))
        db.commit()
        flash("Registered. Please log in.")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        user = get_user_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))
        flash("Invalid credentials.")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/add_venue", methods=["GET", "POST"])
def add_venue():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        location = request.form.get("location", "").strip()
        if not name or not location:
            flash("Both name and location are required.")
            return redirect(url_for("add_venue"))
        db = get_db()
        db.execute("INSERT INTO venue (name, location) VALUES (?, ?)", (name, location))
        db.commit() 
        flash("Venue added successfully.")
        return redirect(url_for("index"))
    return render_template("add_venue.html")

@app.route("/venues")
@login_required
def list_venues():
    db = get_db()
    cur = db.execute("SELECT * FROM venue ORDER BY name")
    venues = cur.fetchall()
    return render_template("venues.html", venues=venues)

@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/add", methods=["POST"])
@login_required
def add():
    title = request.form.get("title", "").strip()
    date = request.form.get("date", "")
    time = request.form.get("time", "")
    notes = request.form.get("notes", "").strip()
    if not title:
        flash("Task title required.")
        return redirect(url_for("index"))
    db = get_db()
    db.execute(
        "INSERT INTO schedule (user_id, title, date, time, notes) VALUES (?, ?, ?, ?, ?)",
        (session["user_id"], title, date or None, time or None, notes or None)
    )
    db.commit()
    return redirect(url_for("index"))

@app.route("/delete/<int:task_id>", methods=["POST"])
@login_required
def delete(task_id):
    db = get_db()
    # ensure task belongs to user
    db.execute("DELETE FROM schedule WHERE id = ? AND user_id = ?", (task_id, session["user_id"]))
    db.commit()
    return redirect(url_for("index"))

@app.route("/edit/<int:task_id>", methods=["GET", "POST"])
@login_required
def edit(task_id):
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        date = request.form.get("date", "")
        time = request.form.get("time", "")
        notes = request.form.get("notes", "").strip()
        if not title:
            flash("Title required.")
            return redirect(url_for("edit", task_id=task_id))
        db.execute(
            "UPDATE schedule SET title=?, date=?, time=?, notes=? WHERE id=? AND user_id=?",
            (title, date or None, time or None, notes or None, task_id, session["user_id"])
        )
        db.commit()
        return redirect(url_for("index"))
    cur = db.execute("SELECT * FROM schedule WHERE id = ? AND user_id = ?", (task_id, session["user_id"]))
    task = cur.fetchone()
    if not task:
        flash("Task not found.")
        return redirect(url_for("index"))
    return render_template("edit.html", task=task)

@app.route("/debug_db")
def debug_db():
    db = get_db()
    venues = db.execute("SELECT * FROM venue").fetchall()
    schedules = db.execute("SELECT * FROM schedule").fetchall()
    return f"Venues: {venues}<br>Schedules: {schedules}"

# ---------- run ----------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)

# No code changes needed. Use a VS Code SQLite extension to view scheduler.db.
