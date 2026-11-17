
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "prepmaster-development-key-change-before-deployment"
)

# DATABASE PATH
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "prepmaster.db")


# DATABASE CONNECTION
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# INITIALIZE DATABASE
def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullname TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            score INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    """)

    conn.commit()
    conn.close()


# LOGIN PROTECTION
def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "student_id" not in session:
            flash("Please log in to access this feature.")
            return redirect(url_for("login"))

        return route_function(*args, **kwargs)

    return wrapper


# HOME
@app.route("/")
def home():
    return render_template("index.html")


# DASHBOARD
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


# VIDEO LESSONS
@app.route("/videos")
@login_required
def videos():
    return render_template("videos.html")


# INTERVIEW QUESTIONS
@app.route("/interview-questions")
@login_required
def interview_questions():
    return render_template("interview_questions.html")


# MOCK TESTS
@app.route("/mock-test")
@login_required
def mock_test():
    return render_template("mock_test.html")


# SAVE MOCK TEST RESULT
@app.route("/save-test-result", methods=["POST"])
@login_required
def save_test_result():

    data = request.get_json(silent=True)

    if not data:
        data = request.form

    subject = str(data.get("subject", "")).strip()

    allowed_subjects = [
        "C Programming",
        "Python Programming",
        "Java Programming",
        "SQL & DBMS",
        "Data Structures",
        "Aptitude"
    ]

    if subject not in allowed_subjects:
        return jsonify({
            "success": False,
            "message": "Invalid subject: " + subject
        }), 400

    try:
        score = int(data.get("score"))
        total_questions = int(data.get("total_questions"))

    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Score or total questions is missing."
        }), 400

    if total_questions != 10 or score < 0 or score > total_questions:
        return jsonify({
            "success": False,
            "message": "Invalid test result."
        }), 400

    conn = get_db_connection()

    try:
        cursor = conn.execute("""
            INSERT INTO test_results
            (student_id, subject, score, total_questions)
            VALUES (?, ?, ?, ?)
        """, (
            session["student_id"],
            subject,
            score,
            total_questions
        ))

        conn.commit()

        saved_id = cursor.lastrowid

        return jsonify({
            "success": True,
            "message": "Your mock test result has been saved!",
            "result_id": saved_id
        })

    except sqlite3.Error as error:
        conn.rollback()

        return jsonify({
            "success": False,
            "message": "Database error: " + str(error)
        }), 500

    finally:
        conn.close()


# STUDENT PROGRESS
@app.route("/progress")
@login_required
def progress():

    student_id = session["student_id"]
    conn = get_db_connection()

    summary = conn.execute("""
        SELECT
            COUNT(*) AS total_tests,
            COALESCE(SUM(score), 0) AS total_score,
            COALESCE(SUM(total_questions), 0) AS total_questions,
            COALESCE(
                MAX(
                    CAST(score AS FLOAT) * 100.0 /
                    NULLIF(total_questions, 0)
                ), 0
            ) AS best_score,
            COUNT(DISTINCT subject) AS subjects_practised
        FROM test_results
        WHERE student_id = ?
    """, (student_id,)).fetchone()

    total_tests = summary["total_tests"]

    if summary["total_questions"] > 0:
        average_score = round(
            summary["total_score"] * 100.0 /
            summary["total_questions"]
        )
    else:
        average_score = 0

    best_score = round(summary["best_score"])
    subjects_practised = summary["subjects_practised"]

    subject_rows = conn.execute("""
        SELECT
            subject,
            ROUND(
                SUM(score) * 100.0 /
                NULLIF(SUM(total_questions), 0)
            ) AS average
        FROM test_results
        WHERE student_id = ?
        GROUP BY subject
        ORDER BY subject
    """, (student_id,)).fetchall()

    subject_progress = [
        {
            "name": row["subject"],
            "average": row["average"] or 0
        }
        for row in subject_rows
    ]

    recent_attempts = conn.execute("""
        SELECT
            subject,
            score,
            total_questions,
            strftime('%d-%m-%Y', attempted_at) AS date
        FROM test_results
        WHERE student_id = ?
        ORDER BY attempted_at DESC, id DESC
        LIMIT 10
    """, (student_id,)).fetchall()

    conn.close()

    return render_template(
        "progress.html",
        total_tests=total_tests,
        average_score=average_score,
        best_score=best_score,
        subjects_practised=subjects_practised,
        subject_progress=subject_progress,
        recent_attempts=recent_attempts
    )


# REGISTER
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        fullname = request.form.get("fullname", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not fullname or not email or not password:
            flash("Please fill in all the fields.")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.")
            return redirect(url_for("register"))

        password_hash = generate_password_hash(password)

        conn = get_db_connection()

        try:
            conn.execute("""
                INSERT INTO students
                (fullname, email, password_hash)
                VALUES (?, ?, ?)
            """, (fullname, email, password_hash))

            conn.commit()

            flash("Registration successful! Please log in.")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("This email is already registered.")

        finally:
            conn.close()

    return render_template("register.html")


# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db_connection()

        student = conn.execute(
            "SELECT * FROM students WHERE email = ?",
            (email,)
        ).fetchone()

        conn.close()

        if student and check_password_hash(
            student["password_hash"], password
        ):

            session.clear()
            session["student_id"] = student["id"]
            session["student_name"] = student["fullname"]

            flash("Login successful!")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


# LOGOUT
@app.route("/logout")
def logout():

    session.clear()
    flash("You have been logged out.")

    return redirect(url_for("home"))


# INITIALIZE DATABASE ON STARTUP
init_db()


# RUN APPLICATION
if __name__ == "__main__":
    app.run(debug=True)
        
