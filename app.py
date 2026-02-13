"""
ATILIM UNIVERSITY
CMPE341 – Database Design and Management
2025–2026 Fall Semester

Project Title:
Film-Ticket Reservation System

Description:
This Flask application provides a web-based interface that allows
administrators and users to interact with an Oracle database. The system
supports customer management and also basic cinema operations such as
listing films/showtimes, ticket management, and a simple ticket purchase flow.
"""

from flask import Flask, render_template, request, redirect, url_for
import re
import oracledb

# -------------------------------------------------
# Oracle Instant Client initialization (thick mode)
# -------------------------------------------------
oracledb.init_oracle_client(lib_dir=r"C:\oracle\instantclient_21_19")

app = Flask(__name__)

def get_connection():
    return oracledb.connect(
        user="hr",
        password="hr",
        dsn="localhost:1521/XE"
    )

# -------------------------------
# Helpers
# -------------------------------
def is_digits(s: str) -> bool:
    return bool(re.fullmatch(r"\d+", s or ""))

def render_message(title: str, message: str, back_url: str):
    return render_template("message.html", title=title, message=message, back_url=back_url)

# -------------------------------
# Homepage
# -------------------------------
@app.route("/")
def index():
    return render_template("index.html")

# -------------------------------
# Admin panel
# -------------------------------
@app.route("/admin")
def admin():
    return render_template("admin.html")

# -------------------------------
# Films & showtimes list (User-side)
# -------------------------------
@app.route("/films")
def films():
    """
    Shows films and their showtimes ordered by date.
    Helps demonstrate 'Pzt su film, Sali su film' by ShowDate ordering.
    """
    con = get_connection()
    cur = con.cursor()

    # Film list with showtimes
    cur.execute("""
        SELECT
            s.ShowDate,
            s.StartTime,
            h.Name AS HallName,
            f.Name AS FilmName,
            f.Type,
            f.Duration,
            f.Explanation,
            s.ShowtimeID
        FROM Showtime s
        JOIN Film f ON f.FilmID = s.FilmID
        JOIN Hall h ON h.HallID = s.HallID
        ORDER BY s.ShowDate, s.StartTime
    """)
    rows = cur.fetchall()

    cur.close()
    con.close()

    return render_template("films.html", rows=rows)

# -------------------------------
# Showtimes management (Admin)
# -------------------------------
@app.route("/admin/showtimes")
def showtimes():
    con = get_connection()
    cur = con.cursor()
    cur.execute("""
        SELECT
            s.ShowtimeID, s.ShowDate, s.StartTime,
            f.Name, h.Name
        FROM Showtime s
        JOIN Film f ON f.FilmID = s.FilmID
        JOIN Hall h ON h.HallID = s.HallID
        ORDER BY s.ShowDate, s.StartTime
    """)
    rows = cur.fetchall()
    cur.close()
    con.close()
    return render_template("showtimes.html", rows=rows)

@app.route("/admin/edit_showtime/<int:showtime_id>", methods=["GET", "POST"])
def edit_showtime(showtime_id):
    """
    Update show date and start time of a showtime (hocanın 'saat değiştiremiyor' eleştirisini çözer).
    """
    con = get_connection()
    cur = con.cursor()

    if request.method == "POST":
        showdate = request.form.get("showdate", "").strip()   # YYYY-MM-DD
        starttime = request.form.get("starttime", "").strip() # HH:MM

        # Basic validation
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", showdate):
            cur.close(); con.close()
            return render_message("Invalid input", "ShowDate must be in YYYY-MM-DD format.", url_for("showtimes"))
        if not re.fullmatch(r"\d{2}:\d{2}", starttime):
            cur.close(); con.close()
            return render_message("Invalid input", "StartTime must be in HH:MM format.", url_for("showtimes"))

        # Update
        cur.execute("""
            UPDATE Showtime
            SET ShowDate = TO_DATE(:1, 'YYYY-MM-DD'),
                StartTime = :2
            WHERE ShowtimeID = :3
        """, [showdate, starttime, showtime_id])
        con.commit()

        cur.close()
        con.close()
        return redirect(url_for("showtimes"))

    # GET: current values
    cur.execute("""
        SELECT ShowtimeID, TO_CHAR(ShowDate, 'YYYY-MM-DD') AS ShowDate, StartTime
        FROM Showtime
        WHERE ShowtimeID = :1
    """, [showtime_id])
    row = cur.fetchone()

    cur.close()
    con.close()

    if not row:
        return render_message("Not found", "Showtime not found.", url_for("showtimes"))

    return render_template("edit_showtime.html", row=row)

# -------------------------------
# Ticket list / delete / update (Admin)
# -------------------------------
@app.route("/admin/tickets")
def tickets():
    """
    Shows TicketID + film + date/time + seat + price.
    This directly answers: 'Biletin idleri' and 'Ticket UI da gorunsun'
    """
    con = get_connection()
    cur = con.cursor()
    cur.execute("""
        SELECT
            t.TicketID,
            t.Price,
            t.ShowtimeID,
            t.SeatID,
            s.StartTime,
            TO_CHAR(s.ShowDate, 'YYYY-MM-DD') AS ShowDate,
            f.Name AS FilmName,
            h.Name AS HallName,
            se.SeatNo
        FROM Ticket t
        JOIN Showtime s ON s.ShowtimeID = t.ShowtimeID
        JOIN Film f ON f.FilmID = s.FilmID
        JOIN Hall h ON h.HallID = t.HallID
        JOIN Seat se ON se.SeatID = t.SeatID
        ORDER BY t.TicketID
    """)
    rows = cur.fetchall()
    cur.close()
    con.close()
    return render_template("tickets.html", rows=rows)

@app.route("/admin/delete_ticket/<int:ticket_id>", methods=["POST"])
def delete_ticket(ticket_id):
    """
    Ticket deletion from UI.
    If ticket is referenced by Purchases, we delete purchases row(s) first (clean delete).
    """
    con = get_connection()
    cur = con.cursor()
    try:
        # First remove purchases referencing this ticket
        cur.execute("DELETE FROM Purchases WHERE TicketID = :1", [ticket_id])
        # Then remove the ticket
        cur.execute("DELETE FROM Ticket WHERE TicketID = :1", [ticket_id])
        con.commit()
    except oracledb.DatabaseError as e:
        con.rollback()
        cur.close(); con.close()
        return render_message("Database Error", str(e), url_for("tickets"))

    cur.close()
    con.close()
    return redirect(url_for("tickets"))

@app.route("/admin/edit_ticket/<int:ticket_id>", methods=["GET", "POST"])
def edit_ticket(ticket_id):
    """
    Minimal ticket update:
    - Update Price (hocanın 'update yok' eleştirisini net kapatır)
    """
    con = get_connection()
    cur = con.cursor()

    if request.method == "POST":
        price = request.form.get("price", "").strip()
        if not re.fullmatch(r"\d+(\.\d{1,2})?", price):
            cur.close(); con.close()
            return render_message("Invalid input", "Price must be numeric (e.g., 120 or 120.00).", url_for("tickets"))

        cur.execute("UPDATE Ticket SET Price = :1 WHERE TicketID = :2", [price, ticket_id])
        con.commit()
        cur.close(); con.close()
        return redirect(url_for("tickets"))

    cur.execute("""
        SELECT TicketID, Price
        FROM Ticket
        WHERE TicketID = :1
    """, [ticket_id])
    row = cur.fetchone()

    cur.close(); con.close()

    if not row:
        return render_message("Not found", "Ticket not found.", url_for("tickets"))

    return render_template("edit_ticket.html", row=row)

# -------------------------------
# Simple ticket purchase (User-like flow)
# -------------------------------
@app.route("/buy_ticket", methods=["GET", "POST"])
def buy_ticket():
    """
    Customer-like flow:
    - select customer
    - select showtime
    - see available seats
    - create Ticket + Purchases
    """
    con = get_connection()
    cur = con.cursor()

    # Load customers
    cur.execute("SELECT CustomerID, Name, Surname FROM Customer ORDER BY CustomerID")
    customers = cur.fetchall()

    # Load showtimes
    cur.execute("""
        SELECT s.ShowtimeID, TO_CHAR(s.ShowDate, 'YYYY-MM-DD'), s.StartTime, f.Name, h.Name, s.HallID
        FROM Showtime s
        JOIN Film f ON f.FilmID = s.FilmID
        JOIN Hall h ON h.HallID = s.HallID
        ORDER BY s.ShowDate, s.StartTime
    """)
    showtimes = cur.fetchall()

    # Determine selected showtime (for available seats)
    selected_showtime = request.values.get("showtime_id", "")
    available_seats = []
    hall_id_for_selected = None

    if selected_showtime and is_digits(selected_showtime):
        cur.execute("SELECT HallID FROM Showtime WHERE ShowtimeID = :1", [int(selected_showtime)])
        r = cur.fetchone()
        if r:
            hall_id_for_selected = r[0]
            # Seats NOT already booked for this showtime
            cur.execute("""
                SELECT se.SeatID, se.SeatNo
                FROM Seat se
                WHERE se.HallID = :1
                  AND se.SeatID NOT IN (
                      SELECT t.SeatID FROM Ticket t WHERE t.ShowtimeID = :2
                  )
                ORDER BY se.SeatNo
            """, [hall_id_for_selected, int(selected_showtime)])
            available_seats = cur.fetchall()

    if request.method == "POST":
        customer_id = request.form.get("customer_id", "").strip()
        showtime_id = request.form.get("showtime_id", "").strip()
        seat_id = request.form.get("seat_id", "").strip()
        price = request.form.get("price", "").strip()

        # Validate
        if not (is_digits(customer_id) and is_digits(showtime_id) and is_digits(seat_id)):
            cur.close(); con.close()
            return render_message("Invalid input", "Customer, showtime, and seat must be selected.", url_for("buy_ticket"))
        if not re.fullmatch(r"\d+(\.\d{1,2})?", price):
            cur.close(); con.close()
            return render_message("Invalid input", "Price must be numeric (e.g., 120 or 120.00).", url_for("buy_ticket"))

        customer_id = int(customer_id)
        showtime_id = int(showtime_id)
        seat_id = int(seat_id)

        # Find hall_id from showtime
        cur.execute("SELECT HallID FROM Showtime WHERE ShowtimeID = :1", [showtime_id])
        rr = cur.fetchone()
        if not rr:
            cur.close(); con.close()
            return render_message("Not found", "Showtime not found.", url_for("buy_ticket"))
        hall_id = rr[0]

        try:
            # Ensure seat is still free
            cur.execute("""
                SELECT COUNT(*)
                FROM Ticket
                WHERE ShowtimeID = :1 AND SeatID = :2
            """, [showtime_id, seat_id])
            if cur.fetchone()[0] > 0:
                cur.close(); con.close()
                return render_message("Seat not available", "This seat is already booked for the selected showtime.", url_for("buy_ticket"))

            # New TicketID
            cur.execute("SELECT NVL(MAX(TicketID), 0) + 1 FROM Ticket")
            new_ticket_id = cur.fetchone()[0]

            # Insert ticket
            cur.execute("""
                INSERT INTO Ticket (TicketID, Price, ShowtimeID, SeatID, HallID)
                VALUES (:1, :2, :3, :4, :5)
            """, [new_ticket_id, price, showtime_id, seat_id, hall_id])

            # Insert purchase (ticket linked to customer)
            cur.execute("""
                INSERT INTO Purchases (TicketID, ConsumableID, CustomerID)
                VALUES (:1, NULL, :2)
            """, [new_ticket_id, customer_id])

            con.commit()

        except oracledb.DatabaseError as e:
            con.rollback()
            cur.close(); con.close()
            return render_message("Database Error", str(e), url_for("buy_ticket"))

        cur.close(); con.close()
        return redirect(url_for("tickets"))

    cur.close()
    con.close()

    return render_template(
        "buy_ticket.html",
        customers=customers,
        showtimes=showtimes,
        selected_showtime=selected_showtime,
        available_seats=available_seats
    )

# -------------------------------
# Add Customer
# -------------------------------
@app.route("/add_customer", methods=["GET", "POST"])
def add_customer():
    if request.method == "POST":
        name = request.form["name"].strip()
        surname = request.form["surname"].strip()
        email = request.form["email"].strip()
        phone = request.form["phone"].strip()

        # phone must be numeric due to NUMBER(11)
        if not is_digits(phone):
            return render_message(
                "Invalid phone",
                "Phone number must contain digits only (e.g., 5051234567).",
                url_for("add_customer")
            )

        con = get_connection()
        cur = con.cursor()

        cur.execute("SELECT NVL(MAX(CustomerID), 0) + 1 FROM Customer")
        new_id = cur.fetchone()[0]

        try:
            cur.execute("""
                INSERT INTO Customer (CustomerID, Name, Surname, Email, PhoneNo)
                VALUES (:1, :2, :3, :4, :5)
            """, [new_id, name, surname, email, int(phone)])
            con.commit()
        except oracledb.DatabaseError as e:
            con.rollback()
            cur.close(); con.close()
            return render_message("Database Error", str(e), url_for("add_customer"))

        cur.close()
        con.close()
        return redirect("/add_customer")

    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT * FROM Customer ORDER BY CustomerID")
    customers = cur.fetchall()
    cur.close()
    con.close()

    return render_template("add_customer.html", customers=customers)

# -------------------------------
# Remove Customer
# -------------------------------
@app.route("/remove_customer", methods=["GET", "POST"])
def remove_customer():
    if request.method == "POST":
        cid = request.form["customerid"].strip()

        if not is_digits(cid):
            return render_message("Invalid input", "Customer ID must be numeric.", url_for("remove_customer"))

        con = get_connection()
        cur = con.cursor()
        try:
            cur.execute("DELETE FROM Customer WHERE CustomerID = :1", [int(cid)])
            con.commit()
        except oracledb.IntegrityError:
            con.rollback()
            cur.close(); con.close()
            return render_message(
                "Deletion blocked",
                "This customer has related purchase/ticket records. Delete related purchases first or choose another customer.",
                url_for("remove_customer")
            )
        except oracledb.DatabaseError as e:
            con.rollback()
            cur.close(); con.close()
            return render_message("Database Error", str(e), url_for("remove_customer"))

        cur.close()
        con.close()
        return redirect("/remove_customer")

    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT CustomerID, Name, Surname FROM Customer ORDER BY CustomerID")
    customers = cur.fetchall()
    cur.close()
    con.close()

    return render_template("remove_customer.html", customers=customers)

# -------------------------------
# Run
# -------------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
