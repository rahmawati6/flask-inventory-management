import base64
from datetime import datetime
from functools import wraps
import os
import tempfile

import pymysql
from flask import Flask, flash, g, make_response, redirect, render_template, request, session, url_for
from fpdf import FPDF
from pymysql.cursors import DictCursor


app = Flask(__name__)
app.secret_key = "flask_python6_secret_key"

DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "flask_python6"

app.config["MYSQL_HOST"] = DB_HOST
app.config["MYSQL_USER"] = DB_USER
app.config["MYSQL_PASSWORD"] = DB_PASSWORD
app.config["MYSQL_DB"] = DB_NAME


class MySQLConnection:
    @property
    def connection(self):
        if "mysql_connection" not in g:
            g.mysql_connection = pymysql.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                cursorclass=DictCursor,
            )
        return g.mysql_connection


mysql = MySQLConnection()


@app.teardown_appcontext
def close_mysql_connection(exception=None):
    connection = g.pop("mysql_connection", None)
    if connection is not None:
        connection.close()


def rupiah(value):
    return "Rp {:,.0f}".format(float(value or 0)).replace(",", ".")


app.jinja_env.filters["rupiah"] = rupiah


def status_badge_class(status):
    return {
        "Draft": "status-draft",
        "Finish": "status-final",
        "Rejected": "status-rejected",
        "Pending": "status-draft",
        "Approved": "status-finish",
    }.get(status, "status-draft")


app.jinja_env.filters["status_badge"] = status_badge_class


def approval_flow_message(pengajuan):
    status_admin = pengajuan.get("status_admin") or "Pending"
    status_accounting = pengajuan.get("status_accounting") or "Pending"
    status_manager = pengajuan.get("status_manager") or "Pending"
    status_akhir = pengajuan.get("status") or "Draft"

    if status_admin == "Rejected":
        return "Pengajuan ditolak oleh Admin."
    if status_accounting == "Rejected":
        return "Pengajuan ditolak oleh Accounting."
    if status_manager == "Rejected":
        return "Pengajuan ditolak oleh Manager."
    if status_admin == "Pending":
        return "Menunggu persetujuan admin."
    if status_admin == "Approved" and status_accounting == "Pending":
        return "Admin sudah menyetujui, menunggu verifikasi dana Accounting."
    if status_admin == "Approved" and status_accounting == "Approved" and status_manager == "Pending":
        return "Admin dan Accounting sudah menyetujui, menunggu approval Manager."
    if status_admin == "Approved" and status_accounting == "Approved" and status_manager == "Approved":
        return "Pengajuan sudah disetujui sepenuhnya."
    if status_akhir == "Rejected":
        return "Pengajuan tidak disetujui."
    return "Pengajuan sedang diproses."


def flow_step_class(status):
    return {
        "Approved": "is-approved",
        "Rejected": "is-rejected",
        "Finish": "is-finish",
    }.get(status or "Pending", "is-pending")


def finish_step_class(pengajuan):
    if (
        pengajuan.get("status_admin") == "Rejected"
        or pengajuan.get("status_accounting") == "Rejected"
        or pengajuan.get("status_manager") == "Rejected"
        or pengajuan.get("status") == "Rejected"
    ):
        return "is-rejected"
    if (
        pengajuan.get("status_admin") == "Approved"
        and pengajuan.get("status_accounting") == "Approved"
        and pengajuan.get("status_manager") == "Approved"
        and pengajuan.get("status") == "Finish"
    ):
        return "is-finish"
    return "is-pending"


app.jinja_env.filters["approval_flow_message"] = approval_flow_message
app.jinja_env.filters["flow_step_class"] = flow_step_class
app.jinja_env.filters["finish_step_class"] = finish_step_class


def add_column_if_missing(cur, table_name, column_name, column_definition):
    cur.execute(
        """
        SELECT COUNT(*) AS total
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (DB_NAME, table_name, column_name),
    )
    result = cur.fetchone()
    total = result["total"] if isinstance(result, dict) else result[0]
    if total == 0:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def redirect_for_role():
    role = session.get("role")
    if role == "admin":
        return redirect(url_for("dashboard_admin"))
    if role == "user":
        return redirect(url_for("dashboard_user"))
    if role == "accounting":
        return redirect(url_for("dashboard_accounting"))
    if role == "manager":
        return redirect(url_for("dashboard_manager"))
    return redirect(url_for("login"))


def initialize_database():
    try:
        conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        cur.execute(f"USE {DB_NAME}")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id_user INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100),
                password VARCHAR(100),
                role ENUM('admin','user','accounting','manager')
            )
            """
        )
        cur.execute("ALTER TABLE users MODIFY role ENUM('admin','user','accounting','manager')")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS barang (
                id_barang INT AUTO_INCREMENT PRIMARY KEY,
                nama_barang VARCHAR(100),
                harga DOUBLE,
                stok INT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pengajuan (
                id_pengajuan INT AUTO_INCREMENT PRIMARY KEY,
                kode_pengajuan VARCHAR(30),
                id_user INT,
                tanggal DATETIME DEFAULT CURRENT_TIMESTAMP,
                grand_total DOUBLE,
                status ENUM('Draft','Finish','Rejected') DEFAULT 'Draft'
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pengajuan_detail (
                id_detail INT AUTO_INCREMENT PRIMARY KEY,
                id_pengajuan INT,
                id_barang INT,
                qty INT,
                harga DOUBLE,
                sub_total DOUBLE
            )
            """
        )

        add_column_if_missing(cur, "pengajuan", "approved_by", "VARCHAR(100) NULL")
        add_column_if_missing(cur, "pengajuan", "approved_at", "DATETIME NULL")
        add_column_if_missing(cur, "pengajuan", "rejected_by", "VARCHAR(100) NULL")
        add_column_if_missing(cur, "pengajuan", "rejected_at", "DATETIME NULL")
        add_column_if_missing(cur, "pengajuan", "signature_data", "LONGTEXT NULL")
        add_column_if_missing(cur, "pengajuan", "status_admin", "ENUM('Pending','Approved','Rejected') DEFAULT 'Pending'")
        add_column_if_missing(cur, "pengajuan", "catatan_admin", "TEXT NULL")
        add_column_if_missing(cur, "pengajuan", "status_accounting", "ENUM('Pending','Approved','Rejected') DEFAULT 'Pending'")
        add_column_if_missing(cur, "pengajuan", "catatan_accounting", "TEXT NULL")
        add_column_if_missing(cur, "pengajuan", "signature_accounting", "LONGTEXT NULL")
        add_column_if_missing(cur, "pengajuan", "accounting_approved_by", "VARCHAR(100) NULL")
        add_column_if_missing(cur, "pengajuan", "accounting_approved_at", "DATETIME NULL")
        add_column_if_missing(cur, "pengajuan", "accounting_rejected_by", "VARCHAR(100) NULL")
        add_column_if_missing(cur, "pengajuan", "accounting_rejected_at", "DATETIME NULL")
        add_column_if_missing(cur, "pengajuan", "status_manager", "ENUM('Pending','Approved','Rejected') DEFAULT 'Pending'")
        add_column_if_missing(cur, "pengajuan", "catatan_manager", "TEXT NULL")
        add_column_if_missing(cur, "pengajuan", "signature_manager", "LONGTEXT NULL")
        add_column_if_missing(cur, "pengajuan", "manager_approved_by", "VARCHAR(100) NULL")
        add_column_if_missing(cur, "pengajuan", "manager_approved_at", "DATETIME NULL")
        add_column_if_missing(cur, "pengajuan", "manager_rejected_by", "VARCHAR(100) NULL")
        add_column_if_missing(cur, "pengajuan", "manager_rejected_at", "DATETIME NULL")

        cur.execute(
            """
            UPDATE pengajuan
            SET status_admin = 'Approved',
                catatan_admin = COALESCE(catatan_admin, 'Disetujui oleh Admin')
            WHERE status = 'Finish'
              AND status_admin = 'Pending'
            """
        )
        cur.execute(
            """
            UPDATE pengajuan
            SET status_accounting = 'Approved'
            WHERE status = 'Finish'
              AND status_admin = 'Approved'
              AND status_accounting = 'Pending'
            """
        )
        cur.execute(
            """
            UPDATE pengajuan
            SET status_manager = 'Approved'
            WHERE status = 'Finish'
              AND status_admin = 'Approved'
              AND status_accounting = 'Approved'
              AND status_manager = 'Pending'
            """
        )
        cur.execute(
            """
            UPDATE pengajuan
            SET status_admin = 'Rejected',
                catatan_admin = COALESCE(catatan_admin, 'Ditolak oleh Admin')
            WHERE status = 'Rejected'
              AND status_admin = 'Pending'
              AND status_accounting = 'Pending'
              AND status_manager = 'Pending'
            """
        )

        cur.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                ("admin", "123", "admin"),
            )

        cur.execute("SELECT COUNT(*) FROM users WHERE username = 'user'")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                ("user", "123", "user"),
            )

        cur.execute("SELECT COUNT(*) FROM users WHERE username = 'akuntansi'")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                ("akuntansi", "a123", "accounting"),
            )

        cur.execute("SELECT COUNT(*) FROM users WHERE username = 'manager'")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                ("manager", "m123", "manager"),
            )

        seed_barang = [
            ("Semen Tiga Roda", 68000, 120),
            ("Cat Tembok 5 Kg", 145000, 45),
            ("Pipa PVC 3 Inch", 52000, 80),
            ("Keramik 40x40", 78000, 60),
            ("Pasir Bangunan", 250000, 25),
        ]
        for nama_barang, harga, stok in seed_barang:
            cur.execute("SELECT COUNT(*) FROM barang WHERE nama_barang = %s", (nama_barang,))
            if cur.fetchone()[0] == 0:
                cur.execute(
                    "INSERT INTO barang (nama_barang, harga, stok) VALUES (%s, %s, %s)",
                    (nama_barang, harga, stok),
                )

        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        print("Database belum siap. Pastikan MySQL Laragon aktif dan user root tanpa password.")
        print(exc)


def login_required(role=None):
    # Bisa dipakai seperti materi Praktek 9: @login_required
    # Bisa juga dipakai untuk role khusus: @login_required("admin")
    if callable(role):
        func = role
        role = None

        @wraps(func)
        def wrapper(*args, **kwargs):
            if "login" not in session and "loggedin" not in session:
                flash("Silakan login terlebih dahulu.", "warning")
                return redirect(url_for("login"))
            return func(*args, **kwargs)

        return wrapper

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "login" not in session and "loggedin" not in session:
                flash("Silakan login terlebih dahulu.", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("Anda tidak memiliki akses ke halaman tersebut.", "danger")
                return redirect_for_role()
            return func(*args, **kwargs)

        return wrapper

    return decorator


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        return login()
    if session.get("role") == "admin":
        return redirect(url_for("dashboard_admin"))
    if session.get("role") == "user":
        return redirect(url_for("dashboard_user"))
    if session.get("role") == "accounting":
        return redirect(url_for("dashboard_accounting"))
    if session.get("role") == "manager":
        return redirect(url_for("dashboard_manager"))
    return render_template("login.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT * FROM users WHERE username = %s AND password = %s",
            (username, password),
        )
        user = cur.fetchone()
        cur.close()

        if user:
            session["login"] = True
            session["loggedin"] = True
            session["id_user"] = user["id_user"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash("Login berhasil.", "success")
            if user["role"] == "admin":
                return redirect(url_for("dashboard_admin"))
            if user["role"] == "user":
                return redirect(url_for("dashboard_user"))
            if user["role"] == "accounting":
                return redirect(url_for("dashboard_accounting"))
            if user["role"] == "manager":
                return redirect(url_for("dashboard_manager"))
            return redirect(url_for("login"))

        flash("Username atau password salah.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Anda berhasil logout.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard_admin")
@login_required("admin")
def dashboard_admin():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) AS total FROM barang")
    total_barang = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM pengajuan")
    total_pengajuan = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM pengajuan WHERE status = 'Draft'")
    total_draft = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM pengajuan WHERE status = 'Finish'")
    total_finish = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM pengajuan WHERE status = 'Rejected'")
    total_rejected = cur.fetchone()["total"]
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        ORDER BY p.tanggal DESC
        LIMIT 10
        """
    )
    pengajuan_terbaru = cur.fetchall()
    cur.close()
    return render_template(
        "dashboard_admin.html",
        total_barang=total_barang,
        total_pengajuan=total_pengajuan,
        total_draft=total_draft,
        total_finish=total_finish,
        total_rejected=total_rejected,
        pengajuan_terbaru=pengajuan_terbaru,
    )


@app.route("/dashboard_user")
@login_required("user")
def dashboard_user():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) AS total FROM barang")
    total_barang = cur.fetchone()["total"]
    cur.execute(
        "SELECT COUNT(*) AS total FROM pengajuan WHERE id_user = %s",
        (session["id_user"],),
    )
    total_pengajuan = cur.fetchone()["total"]
    cur.execute(
        "SELECT COUNT(*) AS total FROM pengajuan WHERE id_user = %s AND status = 'Draft'",
        (session["id_user"],),
    )
    total_draft = cur.fetchone()["total"]
    cur.execute(
        "SELECT COUNT(*) AS total FROM pengajuan WHERE id_user = %s AND status = 'Finish'",
        (session["id_user"],),
    )
    total_finish = cur.fetchone()["total"]
    cur.execute(
        """
        SELECT *
        FROM pengajuan
        WHERE id_user = %s
        ORDER BY tanggal DESC
        LIMIT 5
        """,
        (session["id_user"],),
    )
    pengajuan_terbaru = cur.fetchall()
    latest_pengajuan_id = pengajuan_terbaru[0]["id_pengajuan"] if pengajuan_terbaru else None
    cur.close()
    return render_template(
        "dashboard_user.html",
        total_barang=total_barang,
        total_pengajuan=total_pengajuan,
        total_draft=total_draft,
        total_finish=total_finish,
        pengajuan_terbaru=pengajuan_terbaru,
        latest_pengajuan_id=latest_pengajuan_id,
    )


@app.route("/dashboard_accounting")
@login_required("accounting")
def dashboard_accounting():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COALESCE(SUM(grand_total), 0) AS total FROM pengajuan")
    total_dana = cur.fetchone()["total"]
    cur.execute(
        """
        SELECT COUNT(*) AS total
        FROM pengajuan
        WHERE status_admin = 'Approved'
          AND status_accounting = 'Pending'
          AND status = 'Draft'
        """
    )
    menunggu_verifikasi = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM pengajuan WHERE status_accounting = 'Approved'")
    dana_disetujui = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM pengajuan WHERE status_accounting = 'Rejected'")
    dana_ditolak = cur.fetchone()["total"]
    cur.execute("SELECT COALESCE(SUM(grand_total), 0) AS total FROM pengajuan WHERE status IN ('Finish')")
    total_pengeluaran = cur.fetchone()["total"]
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        WHERE p.status_admin = 'Approved'
        ORDER BY p.tanggal DESC
        LIMIT 10
        """
    )
    pengajuan_terbaru = cur.fetchall()
    cur.close()
    return render_template(
        "dashboard_accounting.html",
        total_dana=total_dana,
        menunggu_verifikasi=menunggu_verifikasi,
        dana_disetujui=dana_disetujui,
        dana_ditolak=dana_ditolak,
        total_pengeluaran=total_pengeluaran,
        pengajuan_terbaru=pengajuan_terbaru,
    )


@app.route("/verifikasi_dana")
@app.route("/approval_accounting")
@login_required("accounting")
def approval_accounting():
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        WHERE p.status = 'Draft'
          AND p.status_admin = 'Approved'
          AND p.status_accounting = 'Pending'
        ORDER BY p.tanggal DESC
        """
    )
    data_pengajuan = cur.fetchall()
    cur.close()
    return render_template("approval_accounting.html", data_pengajuan=data_pengajuan)


@app.route("/accounting_approve/<int:id_pengajuan>", methods=["POST"])
@login_required("accounting")
def accounting_approve(id_pengajuan):
    return redirect(url_for("tanda_tangan_accounting", id_pengajuan=id_pengajuan))


@app.route("/tanda_tangan_accounting/<int:id_pengajuan>", methods=["GET", "POST"])
@login_required("accounting")
def tanda_tangan_accounting(id_pengajuan):
    catatan = request.form.get("catatan_accounting", "")
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        WHERE p.id_pengajuan = %s
          AND p.status = 'Draft'
          AND p.status_admin = 'Approved'
          AND p.status_accounting = 'Pending'
        """,
        (id_pengajuan,),
    )
    pengajuan = cur.fetchone()

    if not pengajuan:
        cur.close()
        flash("Pengajuan tidak tersedia untuk approval Accounting.", "warning")
        return redirect(url_for("approval_accounting"))

    signature_data = request.form.get("signature_data", "")
    if request.method == "POST" and signature_data:
        cur.execute(
            """
        UPDATE pengajuan
        SET status_accounting = 'Approved',
                catatan_accounting = %s,
                signature_accounting = %s,
                accounting_approved_by = %s,
                accounting_approved_at = NOW(),
                accounting_rejected_by = NULL,
                accounting_rejected_at = NULL
        WHERE id_pengajuan = %s
          AND status = 'Draft'
              AND status_admin = 'Approved'
              AND status_accounting = 'Pending'
        """,
            (catatan, signature_data, session["username"], id_pengajuan),
        )
        mysql.connection.commit()
        cur.close()
        flash("Dana pengajuan berhasil disetujui Accounting dan dikirim ke Manager.", "success")
        return redirect(url_for("approval_accounting"))

    cur.close()
    return render_template(
        "tanda_tangan_pengajuan.html",
        pengajuan=pengajuan,
        page_title="Approve Dana & Tanda Tangan",
        page_description="Buat tanda tangan digital Accounting untuk verifikasi dana pengajuan.",
        signature_heading="Area Tanda Tangan Accounting",
        signature_role="Accounting",
        signature_button="Simpan Approve Dana & Tanda Tangan",
        back_endpoint="approval_accounting",
        sidebar_role="accounting",
        catatan_name="catatan_accounting",
        catatan_value=catatan,
    )


@app.route("/accounting_reject/<int:id_pengajuan>", methods=["POST"])
@login_required("accounting")
def accounting_reject(id_pengajuan):
    catatan = request.form.get("catatan_accounting", "")
    cur = mysql.connection.cursor()
    cur.execute(
        """
        UPDATE pengajuan
        SET status_accounting = 'Rejected',
            catatan_accounting = %s,
            status = 'Rejected',
            rejected_by = %s,
            rejected_at = NOW(),
            accounting_rejected_by = %s,
            accounting_rejected_at = NOW(),
            signature_accounting = NULL
        WHERE id_pengajuan = %s
          AND status = 'Draft'
          AND status_admin = 'Approved'
          AND status_accounting = 'Pending'
        """,
        (catatan, session["username"], session["username"], id_pengajuan),
    )
    mysql.connection.commit()
    cur.close()
    flash("Dana pengajuan ditolak Accounting.", "success")
    return redirect(url_for("approval_accounting"))


@app.route("/histori_accounting")
@login_required("accounting")
def histori_accounting():
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        ORDER BY p.tanggal DESC
        """
    )
    data_pengajuan = cur.fetchall()
    cur.close()
    return render_template("histori_accounting.html", data_pengajuan=data_pengajuan)


@app.route("/dashboard_manager")
@login_required("manager")
def dashboard_manager():
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) AS total FROM pengajuan")
    total_pengajuan = cur.fetchone()["total"]
    cur.execute(
        """
        SELECT COUNT(*) AS total
        FROM pengajuan
        WHERE status_admin = 'Approved'
          AND status_accounting = 'Approved'
          AND status_manager = 'Pending'
          AND status = 'Draft'
        """
    )
    menunggu_approval = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM pengajuan WHERE status_manager = 'Approved'")
    pengajuan_disetujui = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS total FROM pengajuan WHERE status_manager = 'Rejected'")
    pengajuan_ditolak = cur.fetchone()["total"]
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        WHERE p.status_admin = 'Approved'
          AND p.status_accounting = 'Approved'
        ORDER BY p.tanggal DESC
        LIMIT 10
        """
    )
    pengajuan_terbaru = cur.fetchall()
    cur.close()
    return render_template(
        "dashboard_manager.html",
        total_pengajuan=total_pengajuan,
        menunggu_approval=menunggu_approval,
        pengajuan_disetujui=pengajuan_disetujui,
        pengajuan_ditolak=pengajuan_ditolak,
        pengajuan_terbaru=pengajuan_terbaru,
    )


@app.route("/approval_manager")
@login_required("manager")
def approval_manager():
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        WHERE p.status_admin = 'Approved'
          AND p.status_accounting = 'Approved'
          AND p.status_manager = 'Pending'
          AND p.status = 'Draft'
        ORDER BY p.tanggal DESC
        """
    )
    data_pengajuan = cur.fetchall()
    cur.close()
    return render_template("approval_manager.html", data_pengajuan=data_pengajuan)


@app.route("/manager_approve/<int:id_pengajuan>", methods=["POST"])
@login_required("manager")
def manager_approve(id_pengajuan):
    return redirect(url_for("tanda_tangan_manager", id_pengajuan=id_pengajuan))


@app.route("/tanda_tangan_manager/<int:id_pengajuan>", methods=["GET", "POST"])
@login_required("manager")
def tanda_tangan_manager(id_pengajuan):
    catatan = request.form.get("catatan_manager", "")
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        WHERE p.id_pengajuan = %s
          AND p.status_admin = 'Approved'
          AND p.status_accounting = 'Approved'
          AND p.status_manager = 'Pending'
          AND p.status = 'Draft'
        """,
        (id_pengajuan,),
    )
    pengajuan = cur.fetchone()

    if not pengajuan:
        cur.close()
        flash("Pengajuan tidak tersedia untuk approval Manager.", "warning")
        return redirect(url_for("approval_manager"))

    signature_data = request.form.get("signature_data", "")
    if request.method == "POST" and signature_data:
        cur.execute(
            """
        UPDATE pengajuan
        SET status_manager = 'Approved',
                catatan_manager = %s,
                signature_manager = %s,
                manager_approved_by = %s,
                manager_approved_at = NOW(),
                manager_rejected_by = NULL,
                manager_rejected_at = NULL,
                status = 'Finish',
                approved_by = %s,
                approved_at = NOW()
        WHERE id_pengajuan = %s
          AND status_accounting = 'Approved'
          AND status_admin = 'Approved'
          AND status_manager = 'Pending'
          AND status = 'Draft'
        """,
            (catatan, signature_data, session["username"], session["username"], id_pengajuan),
        )
        mysql.connection.commit()
        cur.close()
        flash("Pengajuan berhasil disetujui Manager dengan tanda tangan digital.", "success")
        return redirect(url_for("approval_manager"))

    cur.close()
    return render_template(
        "tanda_tangan_pengajuan.html",
        pengajuan=pengajuan,
        page_title="Approve Akhir & Tanda Tangan",
        page_description="Buat tanda tangan digital Manager untuk approval akhir pengajuan.",
        signature_heading="Area Tanda Tangan Manager",
        signature_role="Manager",
        signature_button="Simpan Approve Akhir & Tanda Tangan",
        back_endpoint="approval_manager",
        sidebar_role="manager",
        catatan_name="catatan_manager",
        catatan_value=catatan,
    )


@app.route("/manager_reject/<int:id_pengajuan>", methods=["POST"])
@login_required("manager")
def manager_reject(id_pengajuan):
    catatan = request.form.get("catatan_manager", "")
    cur = mysql.connection.cursor()
    cur.execute(
        """
        UPDATE pengajuan
        SET status_manager = 'Rejected',
            catatan_manager = %s,
            status = 'Rejected',
            rejected_by = %s,
            rejected_at = NOW(),
            manager_rejected_by = %s,
            manager_rejected_at = NOW(),
            signature_manager = NULL
        WHERE id_pengajuan = %s
          AND status_accounting = 'Approved'
          AND status_admin = 'Approved'
          AND status_manager = 'Pending'
          AND status = 'Draft'
        """,
        (catatan, session["username"], session["username"], id_pengajuan),
    )
    mysql.connection.commit()
    cur.close()
    flash("Pengajuan ditolak Manager.", "success")
    return redirect(url_for("approval_manager"))


@app.route("/monitoring_pengajuan")
@app.route("/histori_manager")
@login_required("manager")
def histori_manager():
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        WHERE (p.status_admin = 'Approved' AND p.status_accounting = 'Approved')
           OR p.status_manager <> 'Pending'
        ORDER BY p.tanggal DESC
        """
    )
    data_pengajuan = cur.fetchall()
    cur.close()
    return render_template("histori_manager.html", data_pengajuan=data_pengajuan)


@app.route("/manajemen_user")
@login_required("admin")
def manajemen_user():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id_user, username, role FROM users ORDER BY id_user ASC")
    data_user = cur.fetchall()
    cur.close()
    return render_template("manajemen_user.html", data_user=data_user)


@app.route("/barang")
@login_required()
def barang():
    if session.get("role") not in ["admin", "user"]:
        flash("Anda tidak memiliki akses ke halaman Data Barang.", "danger")
        return redirect_for_role()
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM barang ORDER BY id_barang DESC")
    data_barang = cur.fetchall()
    cur.close()
    return render_template("barang.html", data_barang=data_barang)


@app.route("/tambah_barang", methods=["GET", "POST"])
@login_required("admin")
def tambah_barang():
    if request.method == "POST":
        nama_barang = request.form["nama_barang"]
        harga = request.form["harga"]
        stok = request.form["stok"]

        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO barang (nama_barang, harga, stok) VALUES (%s, %s, %s)",
            (nama_barang, harga, stok),
        )
        mysql.connection.commit()
        cur.close()
        flash("Data barang berhasil ditambahkan.", "success")
        return redirect(url_for("barang"))

    return render_template("tambah_barang.html")


@app.route("/edit_barang/<int:id_barang>", methods=["GET", "POST"])
@login_required("admin")
def edit_barang(id_barang):
    cur = mysql.connection.cursor()
    if request.method == "POST":
        nama_barang = request.form["nama_barang"]
        harga = request.form["harga"]
        stok = request.form["stok"]
        cur.execute(
            "UPDATE barang SET nama_barang = %s, harga = %s, stok = %s WHERE id_barang = %s",
            (nama_barang, harga, stok, id_barang),
        )
        mysql.connection.commit()
        cur.close()
        flash("Data barang berhasil diperbarui.", "success")
        return redirect(url_for("barang"))

    cur.execute("SELECT * FROM barang WHERE id_barang = %s", (id_barang,))
    item = cur.fetchone()
    cur.close()
    if not item:
        flash("Data barang tidak ditemukan.", "danger")
        return redirect(url_for("barang"))
    return render_template("edit_barang.html", item=item)


@app.route("/hapus_barang/<int:id_barang>")
@login_required("admin")
def hapus_barang(id_barang):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM barang WHERE id_barang = %s", (id_barang,))
    mysql.connection.commit()
    cur.close()
    flash("Data barang berhasil dihapus.", "success")
    return redirect(url_for("barang"))


@app.route("/pengajuan_barang", methods=["GET", "POST"])
@login_required("user")
def pengajuan_barang():
    cur = mysql.connection.cursor()
    if request.method == "POST":
        id_barang_list = request.form.getlist("id_barang[]")
        harga_list = request.form.getlist("harga[]")
        qty_list = request.form.getlist("qty[]")
        sub_total_list = request.form.getlist("sub_total[]")

        grand_total = 0
        details = []

        for index in range(len(id_barang_list)):
            if not id_barang_list[index] or not qty_list[index]:
                continue

            qty_int = int(qty_list[index])
            if qty_int <= 0:
                continue

            harga = float(harga_list[index] or 0) if index < len(harga_list) else 0
            sub_total = float(sub_total_list[index] or 0) if index < len(sub_total_list) else 0

            if harga <= 0 or sub_total <= 0:
                cur.execute("SELECT * FROM barang WHERE id_barang = %s", (id_barang_list[index],))
                item = cur.fetchone()
                if not item:
                    continue
                harga = float(item["harga"])
                sub_total = harga * qty_int

            grand_total += sub_total
            details.append((id_barang_list[index], qty_int, harga, sub_total))

        if not details:
            cur.close()
            flash("Minimal pilih satu barang dengan qty lebih dari 0.", "warning")
            return redirect(url_for("pengajuan_barang"))

        kode_pengajuan = "PJG-" + datetime.now().strftime("%Y%m%d%H%M%S")

        cur.execute(
            """
            INSERT INTO pengajuan (kode_pengajuan, id_user, grand_total, status)
            VALUES (%s, %s, %s, %s)
            """,
            (kode_pengajuan, session["id_user"], grand_total, "Draft"),
        )
        mysql.connection.commit()

        id_pengajuan = cur.lastrowid

        for id_barang, qty, harga, sub_total in details:
            cur.execute(
                """
                INSERT INTO pengajuan_detail
                (id_pengajuan, id_barang, qty, harga, sub_total)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (id_pengajuan, id_barang, qty, harga, sub_total),
            )

        mysql.connection.commit()
        cur.close()
        flash("Pengajuan barang berhasil dikirim.", "success")
        return redirect(url_for("histori_pengajuan_user"))

    cur.execute("SELECT * FROM barang ORDER BY nama_barang ASC")
    data_barang = cur.fetchall()
    cur.close()
    return render_template("pengajuan_barang.html", data_barang=data_barang, barang=data_barang)


@app.route("/histori_pengajuan_user")
@login_required("user")
def histori_pengajuan_user():
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT * FROM pengajuan
        WHERE id_user = %s
        ORDER BY tanggal DESC
        """,
        (session["id_user"],),
    )
    data_pengajuan = cur.fetchall()
    cur.close()
    return render_template("histori_pengajuan_user.html", data_pengajuan=data_pengajuan)


@app.route("/approval_pengajuan")
@login_required("admin")
def approval_pengajuan():
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        WHERE p.status = 'Draft'
          AND p.status_admin = 'Pending'
        ORDER BY p.tanggal DESC
        """
    )
    data_pengajuan = cur.fetchall()
    cur.close()
    return render_template("approval_pengajuan.html", data_pengajuan=data_pengajuan)


@app.route("/approve_pengajuan/<int:id_pengajuan>")
@login_required("admin")
def approve_pengajuan(id_pengajuan):
    return redirect(url_for("tanda_tangan_pengajuan", id_pengajuan=id_pengajuan))


@app.route("/tanda_tangan_pengajuan/<int:id_pengajuan>", methods=["GET", "POST"])
@login_required("admin")
def tanda_tangan_pengajuan(id_pengajuan):
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        WHERE p.id_pengajuan = %s
          AND p.status = 'Draft'
          AND p.status_admin = 'Pending'
        """,
        (id_pengajuan,),
    )
    pengajuan = cur.fetchone()

    if not pengajuan:
        cur.close()
        flash("Data pengajuan tidak ditemukan.", "danger")
        return redirect(url_for("approval_pengajuan"))

    if request.method == "POST":
        signature_data = request.form.get("signature_data", "")
        if not signature_data:
            cur.close()
            flash("Silakan buat tanda tangan terlebih dahulu.", "warning")
            return redirect(url_for("tanda_tangan_pengajuan", id_pengajuan=id_pengajuan))

        cur.execute(
            """
            UPDATE pengajuan
            SET status_admin = 'Approved',
                catatan_admin = %s,
                approved_by = %s,
                approved_at = NOW(),
                signature_data = %s,
                rejected_by = NULL,
                rejected_at = NULL
            WHERE id_pengajuan = %s
              AND status = 'Draft'
              AND status_admin = 'Pending'
            """,
            ("Disetujui oleh Admin", session["username"], signature_data, id_pengajuan),
        )
        mysql.connection.commit()
        cur.close()
        flash("Pengajuan disetujui Admin dan dikirim ke Accounting.", "success")
        return redirect(url_for("approval_pengajuan"))

    cur.close()
    return render_template("tanda_tangan_pengajuan.html", pengajuan=pengajuan)


@app.route("/reject_pengajuan/<int:id_pengajuan>")
@login_required("admin")
def reject_pengajuan(id_pengajuan):
    cur = mysql.connection.cursor()
    cur.execute(
        """
        UPDATE pengajuan
        SET status_admin = 'Rejected',
            catatan_admin = 'Ditolak oleh Admin',
            status = 'Rejected',
            rejected_by = %s,
            rejected_at = NOW(),
            approved_by = NULL,
            approved_at = NULL,
            signature_data = NULL
        WHERE id_pengajuan = %s
          AND status = 'Draft'
          AND status_admin = 'Pending'
        """,
        (session["username"], id_pengajuan),
    )
    mysql.connection.commit()
    cur.close()
    flash("Pengajuan berhasil ditolak.", "success")
    return redirect(url_for("approval_pengajuan"))


@app.route("/histori_pengajuan_admin")
@login_required("admin")
def histori_pengajuan_admin():
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        ORDER BY p.tanggal DESC
        """
    )
    data_pengajuan = cur.fetchall()
    cur.close()
    return render_template("histori_pengajuan_admin.html", data_pengajuan=data_pengajuan)


# =========================
# GENERATE PDF DETAIL PENGAJUAN
# =========================
@app.route("/detail_pdf/<int:id_pengajuan>")
@login_required()
def detail_pdf(id_pengajuan):
    cur = mysql.connection.cursor(DictCursor)

    # HEADER PENGAJUAN
    cur.execute(
        """
        SELECT p.*, u.username
        FROM pengajuan p
        JOIN users u ON p.id_user = u.id_user
        WHERE p.id_pengajuan = %s
        """,
        (id_pengajuan,),
    )
    pengajuan = cur.fetchone()

    if not pengajuan:
        cur.close()
        flash("Data pengajuan tidak ditemukan.", "danger")
        return redirect(url_for("index"))

    if session.get("role") == "user" and pengajuan["id_user"] != session.get("id_user"):
        cur.close()
        flash("Anda tidak memiliki akses ke PDF tersebut.", "danger")
        return redirect(url_for("histori_pengajuan_user"))

    # DETAIL BARANG
    cur.execute(
        """
        SELECT d.*, b.nama_barang
        FROM pengajuan_detail d
        JOIN barang b ON d.id_barang = b.id_barang
        WHERE d.id_pengajuan = %s
        ORDER BY d.id_detail ASC
        """,
        (id_pengajuan,),
    )
    details = cur.fetchall()
    cur.close()

    # GENERATE PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "DETAIL PENGAJUAN BARANG", 0, 1, "C")
    pdf.ln(5)

    pdf.set_font("Arial", "", 10)
    pdf.cell(45, 8, "Kode Pengajuan", 0, 0)
    pdf.cell(0, 8, f": {pengajuan['kode_pengajuan']}", 0, 1)
    pdf.cell(45, 8, "User", 0, 0)
    pdf.cell(0, 8, f": {pengajuan['username']}", 0, 1)
    pdf.cell(45, 8, "Tanggal", 0, 0)
    pdf.cell(0, 8, f": {pengajuan['tanggal']}", 0, 1)
    pdf.cell(45, 8, "Status", 0, 0)
    pdf.cell(0, 8, f": {pengajuan['status']}", 0, 1)
    pdf.cell(45, 8, "Status Admin", 0, 0)
    pdf.cell(0, 8, f": {pengajuan.get('status_admin') or 'Pending'}", 0, 1)
    pdf.cell(45, 8, "Catatan Admin", 0, 0)
    pdf.cell(0, 8, f": {pengajuan.get('catatan_admin') or '-'}", 0, 1)
    pdf.cell(45, 8, "Status Accounting", 0, 0)
    pdf.cell(0, 8, f": {pengajuan.get('status_accounting') or 'Pending'}", 0, 1)
    pdf.cell(45, 8, "Catatan Accounting", 0, 0)
    pdf.cell(0, 8, f": {pengajuan.get('catatan_accounting') or '-'}", 0, 1)
    pdf.cell(45, 8, "Status Manager", 0, 0)
    pdf.cell(0, 8, f": {pengajuan.get('status_manager') or 'Pending'}", 0, 1)
    pdf.cell(45, 8, "Catatan Manager", 0, 0)
    pdf.cell(0, 8, f": {pengajuan.get('catatan_manager') or '-'}", 0, 1)
    pdf.ln(5)

    pdf.set_font("Arial", "B", 10)
    pdf.cell(70, 8, "Nama Barang", 1, 0, "C")
    pdf.cell(20, 8, "Qty", 1, 0, "C")
    pdf.cell(45, 8, "Harga", 1, 0, "C")
    pdf.cell(45, 8, "Sub Total", 1, 1, "C")

    pdf.set_font("Arial", "", 10)
    for detail in details:
        pdf.cell(70, 8, str(detail["nama_barang"]), 1, 0)
        pdf.cell(20, 8, str(detail["qty"]), 1, 0, "C")
        pdf.cell(45, 8, rupiah(detail["harga"]), 1, 0, "R")
        pdf.cell(45, 8, rupiah(detail["sub_total"]), 1, 1, "R")

    pdf.set_font("Arial", "B", 10)
    pdf.cell(135, 8, "Grand Total", 1, 0, "R")
    pdf.cell(45, 8, rupiah(pengajuan["grand_total"]), 1, 1, "R")

    def draw_signature_block(title, signer, signed_at, signature_data, x_position, y_position):
        box_width = 55
        pdf.set_xy(x_position, y_position)
        pdf.set_font("Arial", "B", 10)
        pdf.cell(box_width, 6, title, 0, 2, "C")
        pdf.set_font("Arial", "", 8)
        pdf.cell(box_width, 5, "Ditandatangani oleh,", 0, 2, "C")

        signature_path = None
        if signature_data:
            try:
                clean_signature = signature_data.split(",", 1)[1] if "," in signature_data else signature_data
                signature_bytes = base64.b64decode(clean_signature)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_signature:
                    temp_signature.write(signature_bytes)
                    signature_path = temp_signature.name
                pdf.image(signature_path, x=x_position + 5, y=y_position + 14, w=45)
            except Exception:
                pdf.set_xy(x_position, y_position + 22)
                pdf.set_font("Arial", "I", 8)
                pdf.cell(box_width, 5, "Tanda tangan tidak terbaca", 0, 2, "C")
            finally:
                if signature_path and os.path.exists(signature_path):
                    os.remove(signature_path)
        else:
            pdf.set_xy(x_position, y_position + 22)
            pdf.set_font("Arial", "I", 8)
            pdf.cell(box_width, 5, "Belum ada tanda tangan", 0, 2, "C")

        pdf.set_xy(x_position, y_position + 43)
        pdf.set_font("Arial", "B", 9)
        pdf.cell(box_width, 5, str(signer or "-"), 0, 2, "C")
        pdf.set_font("Arial", "", 7)
        pdf.cell(box_width, 4, f"Waktu: {signed_at or '-'}", 0, 2, "C")

    pdf.ln(12)
    signature_blocks = []
    if pengajuan.get("status_admin") == "Approved" or pengajuan.get("signature_data"):
        signature_blocks.append(
            (
                "Admin",
                pengajuan.get("approved_by") or "Admin",
                pengajuan.get("approved_at"),
                pengajuan.get("signature_data"),
            )
        )
    if pengajuan.get("status_accounting") == "Approved" or pengajuan.get("signature_accounting"):
        signature_blocks.append(
            (
                "Accounting",
                pengajuan.get("accounting_approved_by") or "Accounting",
                pengajuan.get("accounting_approved_at"),
                pengajuan.get("signature_accounting"),
            )
        )
    if pengajuan.get("status_manager") == "Approved" or pengajuan.get("signature_manager"):
        signature_blocks.append(
            (
                "Manager",
                pengajuan.get("manager_approved_by") or "Manager",
                pengajuan.get("manager_approved_at"),
                pengajuan.get("signature_manager"),
            )
        )
    if signature_blocks:
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 8, "PERSETUJUAN DAN TANDA TANGAN DIGITAL", 0, 1, "C")
        y_signature = pdf.get_y() + 2
        x_positions = [18, 78, 138]
        for index, block in enumerate(signature_blocks[:3]):
            draw_signature_block(block[0], block[1], block[2], block[3], x_positions[index], y_signature)
        pdf.set_y(y_signature + 55)
        pdf.set_font("Arial", "", 9)
        pdf.cell(0, 6, "Tanda tangan dibuat manual melalui sistem.", 0, 1, "C")
    elif pengajuan["status"] == "Rejected":
        rejected_by = pengajuan.get("rejected_by") or "Admin"
        rejected_at = pengajuan.get("rejected_at") or "-"
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 8, "PENGAJUAN DITOLAK", 0, 1, "R")
        pdf.set_font("Arial", "", 9)
        pdf.cell(0, 6, f"Ditolak oleh: {rejected_by}", 0, 1, "R")
        pdf.cell(0, 6, f"Waktu: {rejected_at}", 0, 1, "R")

    response = make_response(pdf.output(dest="S").encode("latin-1"))
    response.headers.set(
        "Content-Disposition",
        "inline",
        filename=f"detail_pengajuan_{id_pengajuan}.pdf",
    )
    response.headers.set("Content-Type", "application/pdf")
    return response


if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)
