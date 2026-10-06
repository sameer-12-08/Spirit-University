from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DATABASE = "classroom_booking.db"

CLASSROOMS = [
    {"id": 1, "name": "A101 - Lecture Hall", "building": "Block A", "capacity": 40, "equipment": "Projector, Whiteboard, AC, Wi-Fi", "image": "classroom2.jpg"},
    {"id": 2, "name": "A102 - Lecture Hall", "building": "Block A", "capacity": 60, "equipment": "Projector, Whiteboard, AC, Wi-Fi", "image": "classroom1.jpg"},
    {"id": 3, "name": "B201 - Computer Lab", "building": "Block B", "capacity": 50, "equipment": "Computers, Internet, Projector", "image": "classroom5.jpg"},
    {"id": 4, "name": "C301 - Science Lab", "building": "Block C", "capacity": 35, "equipment": "Lab Equipment, Projector, Wi-Fi", "image": "classroom3.jpg"},
    {"id": 5, "name": "Seminar Hall", "building": "Main Block", "capacity": 150, "equipment": "Projector, Audio System, AC", "image": "classroom4.jpg"},
]

USERS = [
    ("admin", "admin@123", "admin"),
    ("faculty", "Faculty@123", "faculty"),
    ("Dinesh", "Spirit@123", "student"),
    ("Hari", "Spirit@123", "student"),
    ("Jai", "Spirit@123", "student"),
    ("Ram", "Spirit@123", "student"),
]

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        classroom_id INTEGER NOT NULL,
        booking_date TEXT NOT NULL,
        time_slot TEXT NOT NULL,
        seats INTEGER NOT NULL,
        purpose TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    for username, password, role in USERS:
        existing = conn.execute(
            "SELECT id FROM users WHERE LOWER(username)=LOWER(?)",
            (username,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET password=?, role=? WHERE id=?",
                (password, role, existing["id"])
            )
        else:
            conn.execute(
                "INSERT INTO users(username,password,role) VALUES(?,?,?)",
                (username, password, role)
            )
    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper

@app.route("/")
def home():
    return redirect(url_for("dashboard" if "username" in session else "login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "").strip().lower()

        conn = get_db()
        user = conn.execute(
            """SELECT * FROM users
               WHERE LOWER(username) = LOWER(?)
                 AND password = ?
                 AND LOWER(role) = LOWER(?)""",
            (identifier, password, role)
        ).fetchone()
        conn.close()

        if user:
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("admin" if user["role"] == "admin" else "dashboard"))

        flash("Invalid ID, password, or role.", "error")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    mine = conn.execute("SELECT COUNT(*) FROM bookings WHERE username=?", (session["username"],)).fetchone()[0]
    conn.close()
    return render_template("dashboard.html", classrooms=CLASSROOMS, total_bookings=total, my_bookings=mine)

@app.route("/classrooms")
@login_required
def classrooms():
    return render_template("classrooms.html", classrooms=CLASSROOMS)

@app.route("/book/<int:classroom_id>", methods=["GET", "POST"])
@login_required
def book(classroom_id):
    classroom = next((r for r in CLASSROOMS if r["id"] == classroom_id), None)
    if not classroom:
        flash("Classroom not found.", "error")
        return redirect(url_for("classrooms"))

    if request.method == "POST":
        date = request.form.get("booking_date", "")
        time_slot = request.form.get("time_slot", "")
        purpose = request.form.get("purpose", "").strip()
        try:
            seats = int(request.form.get("seats", "0"))
        except ValueError:
            seats = 0

        if not date or not time_slot or not purpose:
            flash("Please complete all fields.", "error")
            return redirect(url_for("book", classroom_id=classroom_id))

        if seats < 1 or seats > 5:
            flash("You can book 1 to 5 seats.", "error")
            return redirect(url_for("book", classroom_id=classroom_id))

        try:
            start, end = [x.strip() for x in time_slot.split(" - ", 1)]
            if end <= start:
                raise ValueError
        except ValueError:
            flash("Please select a valid start and end time.", "error")
            return redirect(url_for("book", classroom_id=classroom_id))

        conn = get_db()
        conflict = conn.execute(
            """SELECT id FROM bookings
               WHERE classroom_id=? AND booking_date=? AND time_slot=?""",
            (classroom_id, date, time_slot)
        ).fetchone()

        if conflict:
            conn.close()
            flash("That exact classroom time is already booked.", "error")
            return redirect(url_for("book", classroom_id=classroom_id))

        conn.execute(
            """INSERT INTO bookings
               (username,classroom_id,booking_date,time_slot,seats,purpose,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (session["username"], classroom_id, date, time_slot, seats, purpose,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        conn.close()
        flash("Classroom booked successfully.", "success")
        return redirect(url_for("my_bookings"))

    return render_template("booking.html", classroom=classroom)

@app.route("/my-bookings")
@login_required
def my_bookings():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM bookings WHERE username=? ORDER BY booking_date, id",
        (session["username"],)
    ).fetchall()
    conn.close()

    bookings = []
    for row in rows:
        room = next((r for r in CLASSROOMS if r["id"] == row["classroom_id"]), None)
        bookings.append({
            "id": row["id"], "classroom": room["name"] if room else "Unknown",
            "building": room["building"] if room else "",
            "date": row["booking_date"], "time": row["time_slot"],
            "seats": row["seats"], "purpose": row["purpose"]
        })
    return render_template("my_bookings.html", bookings=bookings)

@app.route("/cancel/<int:booking_id>")
@login_required
def cancel_booking(booking_id):
    conn = get_db()
    conn.execute("DELETE FROM bookings WHERE id=? AND username=?", (booking_id, session["username"]))
    conn.commit()
    conn.close()
    flash("Booking cancelled.", "success")
    return redirect(url_for("my_bookings"))

@app.route("/admin")
@login_required
@admin_required
def admin():
    conn = get_db()
    rows = conn.execute("SELECT * FROM bookings ORDER BY booking_date, id").fetchall()
    users = conn.execute("SELECT id,username,role FROM users ORDER BY role,username").fetchall()
    conn.close()

    bookings = []
    for row in rows:
        room = next((r for r in CLASSROOMS if r["id"] == row["classroom_id"]), None)
        bookings.append({
            "id": row["id"], "username": row["username"],
            "classroom": room["name"] if room else "Unknown",
            "date": row["booking_date"], "time": row["time_slot"],
            "seats": row["seats"], "purpose": row["purpose"]
        })
    return render_template("admin.html", bookings=bookings, users=users)

@app.route("/admin/delete/<int:booking_id>")
@login_required
@admin_required
def admin_delete_booking(booking_id):
    conn = get_db()
    conn.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
    conn.commit()
    conn.close()
    flash("Booking deleted.", "success")
    return redirect(url_for("admin"))

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
