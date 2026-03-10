from flask import render_template, request, redirect, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, resequence_all_ids


# -------------------- Register --------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, password, "student")
            )
            conn.commit()
            flash("Registration successful!", "success")
            return redirect("/login")
        except sqlite3.IntegrityError:
            flash("User already exists!", "error")

        conn.close()

    return render_template("register.html")


# -------------------- Login --------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, password, role, is_blocked FROM users WHERE username=?",
            (username,),
        )
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            if user[4] == 1:
                flash("Your account is blocked by admin.", "error")
                return redirect("/login")

            session["user_id"] = user[0]
            session["username"] = user[1]
            session["role"] = user[3]

            flash("Login successful!", "success")

            if user[3] == "admin":
                return redirect("/admin")
            return redirect("/")

        flash("Invalid credentials!", "error")

    return render_template("login.html")


# -------------------- Logout --------------------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect("/login")


# -------------------- Home / About --------------------
@app.route("/")
def home():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, fee, duration, image FROM courses ORDER BY id ASC LIMIT 3")
    featured_courses = cursor.fetchall()
    conn.close()

    return render_template("home.html", featured_courses=featured_courses)


@app.route("/about")
def about():
    return render_template("about.html")


# -------------------- Courses Page --------------------
@app.route("/courses")
def courses():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM courses")
    courses_list = cursor.fetchall()

    enrolled = []
    if session.get("user_id"):
        cursor.execute(
            "SELECT course_id FROM enrollments WHERE user_id=?",
            (session["user_id"],)
        )
        enrolled = [row[0] for row in cursor.fetchall()]

    conn.close()

    return render_template(
        "courses.html",
        courses=courses_list,
        enrolled_courses=enrolled
    )


# -------------------- Enroll --------------------
@app.route("/enroll/<int:course_id>")
def enroll(course_id):
    if session.get("role") != "student":
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT is_blocked FROM users WHERE id=?", (session["user_id"],))
    user = cursor.fetchone()

    if user[0] == 1:
        flash("You are blocked by admin!", "error")
        conn.close()
        return redirect("/courses")

    try:
        cursor.execute(
            "INSERT INTO enrollments (user_id, course_id) VALUES (?, ?)",
            (session["user_id"], course_id)
        )
        conn.commit()
        flash("Enrollment successful!", "success")
    except sqlite3.IntegrityError:
        flash("Already enrolled!", "error")

    conn.close()
    return redirect("/courses")


# -------------------- Student Dashboard --------------------
@app.route("/student/dashboard")
def student_dashboard():
    if session.get("role") != "student":
        return "Unauthorized"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT courses.name, courses.fee, courses.duration
        FROM enrollments
        JOIN courses ON enrollments.course_id = courses.id
        WHERE enrollments.user_id=?
    """, (session["user_id"],))

    courses = cursor.fetchall()
    conn.close()

    return render_template("student_dashboard.html", courses=courses)


# -------------------- Admin Dashboard --------------------
@app.route("/admin")
def admin_dashboard():
    if session.get("role") != "admin":
        return "Unauthorized"
    return render_template("admin_dashboard.html")


# -------------------- Admin Students --------------------
@app.route("/admin/admin_students", methods=["GET", "POST"])
@app.route("/admin/students", methods=["GET", "POST"])
def admin_students():
    if session.get("role") != "admin":
        return "Unauthorized"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":
        student_id = request.form.get("student_id")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username:
            flash("Username is required.", "error")
            conn.close()
            return redirect("/admin/students")

        try:
            if student_id:
                if password:
                    hashed_password = generate_password_hash(password)
                    cursor.execute(
                        "UPDATE users SET username=?, password=? WHERE id=? AND role='student'",
                        (username, hashed_password, student_id),
                    )
                else:
                    cursor.execute(
                        "UPDATE users SET username=? WHERE id=? AND role='student'",
                        (username, student_id),
                    )
                flash("Student updated successfully!", "success")
            else:
                if not password:
                    flash("Password is required for new student.", "error")
                    conn.close()
                    return redirect("/admin/students")

                hashed_password = generate_password_hash(password)
                cursor.execute(
                    "INSERT INTO users (username, password, role, is_blocked) VALUES (?, ?, 'student', 0)",
                    (username, hashed_password),
                )
                flash("Student added successfully!", "success")

            conn.commit()
        except sqlite3.IntegrityError:
            flash("Username already exists.", "error")

        conn.close()
        return redirect("/admin/students")

    edit_id = request.args.get("edit")
    edit_student = None
    if edit_id:
        cursor.execute(
            "SELECT id, username, is_blocked FROM users WHERE id=? AND role='student'",
            (edit_id,),
        )
        edit_student = cursor.fetchone()

    cursor.execute("SELECT id, username, is_blocked FROM users WHERE role='student' ORDER BY id ASC")
    students = cursor.fetchall()

    conn.close()
    return render_template("admin_students.html", students=students, edit_student=edit_student)


@app.route("/admin/update_student/<int:user_id>")
def update_student(user_id):
    if session.get("role") != "admin":
        return "Unauthorized"
    return redirect(f"/admin/students?edit={user_id}")


@app.route("/admin/toggle_block/<int:user_id>")
def toggle_block(user_id):
    if session.get("role") != "admin":
        return "Unauthorized"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT is_blocked FROM users WHERE id=?", (user_id,))
    status = cursor.fetchone()[0]

    new_status = 0 if status == 1 else 1

    cursor.execute("UPDATE users SET is_blocked=? WHERE id=?", (new_status, user_id))
    conn.commit()
    conn.close()

    flash("User status updated!", "success")
    return redirect("/admin/students")


@app.route("/admin/delete_student/<int:user_id>")
def delete_student(user_id):
    if session.get("role") != "admin":
        return "Unauthorized"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
    cursor.execute("DELETE FROM enrollments WHERE user_id=?", (user_id,))
    resequence_all_ids(conn)
    conn.commit()
    conn.close()

    flash("Student deleted!", "success")
    return redirect("/admin/students")


# -------------------- Admin Enrollments --------------------
@app.route("/admin/enrollments")
def admin_enrollments():
    if session.get("role") != "admin":
        return "Unauthorized"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT users.username, courses.name
        FROM enrollments
        JOIN users ON enrollments.user_id = users.id
        JOIN courses ON enrollments.course_id = courses.id
        ORDER BY users.username ASC, courses.name ASC
    """)
    data = cursor.fetchall()
    conn.close()

    return render_template("admin_enrollments.html", data=data)


# -------------------- Admin Courses --------------------
@app.route("/admin/courses", methods=["GET", "POST"])
def admin_courses():
    if session.get("role") != "admin":
        return "Unauthorized"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":
        course_id = request.form.get("course_id")
        name = request.form["name"]
        fee = request.form["fee"]
        duration = request.form["duration"]
        image = request.form["image"]

        if course_id:
            cursor.execute("""
                UPDATE courses
                SET name=?, fee=?, duration=?, image=?
                WHERE id=?
            """, (name, fee, duration, image, course_id))
            flash("Course updated!", "success")
        else:
            cursor.execute("""
                INSERT INTO courses (name, fee, duration, image)
                VALUES (?, ?, ?, ?)
            """, (name, fee, duration, image))
            flash("Course added!", "success")

        conn.commit()
        return redirect("/admin/courses")

    edit_id = request.args.get("edit")
    edit_course = None
    if edit_id:
        cursor.execute("SELECT * FROM courses WHERE id=?", (edit_id,))
        edit_course = cursor.fetchone()

    cursor.execute("SELECT * FROM courses")
    courses = cursor.fetchall()
    conn.close()

    return render_template("admin_courses.html", courses=courses, edit_course=edit_course)


@app.route("/admin/update_course/<int:course_id>")
def update_course(course_id):
    if session.get("role") != "admin":
        return "Unauthorized"
    return redirect(f"/admin/courses?edit={course_id}")


@app.route("/admin/delete_course/<int:course_id>")
def delete_course(course_id):
    if session.get("role") != "admin":
        return "Unauthorized"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM courses WHERE id=?", (course_id,))
    cursor.execute("DELETE FROM enrollments WHERE course_id=?", (course_id,))
    resequence_all_ids(conn)

    conn.commit()
    conn.close()

    flash("Course deleted!", "success")
    return redirect("/admin/courses")
