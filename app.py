
from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from fare_engine import calculate_fare, calculate_all_fares

app = Flask(__name__)
app.secret_key = "railbook-local-secret"

DATABASE = "database.db"

CLASS_LABELS = {
    "sleeper": "Sleeper (SL)",
    "3A": "AC 3 Tier (3A)",
    "2A": "AC 2 Tier (2A)",
    "1A": "First AC (1A)"
}

SEAT_COLUMNS = {
    "sleeper": "sleeper_seats",
    "3A": "ac3_seats",
    "2A": "ac2_seats",
    "1A": "ac1_seats"
}


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def get_journey_distance(conn, train_id, source, destination):
    stations = conn.execute(
        """
        SELECT station_name, distance_from_source
        FROM train_stations
        WHERE train_id = ?
        ORDER BY stop_order
        """,
        (train_id,)
    ).fetchall()

    source_station = next(
        (s for s in stations if s["station_name"].strip().lower() == source.strip().lower()),
        None
    )
    destination_station = next(
        (s for s in stations if s["station_name"].strip().lower() == destination.strip().lower()),
        None
    )

    if not source_station or not destination_station:
        return None

    distance = (destination_station["distance_from_source"] or 0) - (source_station["distance_from_source"] or 0)
    return max(0, distance)


def get_train_fares(conn, train, source=None, destination=None):
    source = source or train["source"]
    destination = destination or train["destination"]
    distance = get_journey_distance(conn, train["id"], source, destination)

    if distance is None or distance <= 0:
        return {
            "distance": distance,
            "fares": {}
        }

    engine_fares = calculate_all_fares(
        distance,
        train["train_type"] or "NORMAL"
    )

    # The application uses "sleeper" internally, while the fare engine
    # uses the standard railway class code "SL". Keep the UI/API keys
    # consistent with the existing templates.
    fares = {
        "sleeper": engine_fares["SL"],
        "3A": engine_fares["3A"],
        "2A": engine_fares["2A"],
        "1A": engine_fares["1A"]
    }

    return {
        "distance": distance,
        "fares": fares
    }


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS trains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            train_number TEXT UNIQUE NOT NULL,
            train_name TEXT NOT NULL,
            source TEXT NOT NULL,
            destination TEXT NOT NULL,
            departure TEXT NOT NULL,
            arrival TEXT NOT NULL,
            duration TEXT NOT NULL,
            sleeper_seats INTEGER DEFAULT 0,
            ac3_seats INTEGER DEFAULT 0,
            ac2_seats INTEGER DEFAULT 0,
            ac1_seats INTEGER DEFAULT 0,
            train_type TEXT DEFAULT 'NORMAL'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pnr TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            train_id INTEGER NOT NULL,
            journey_date TEXT NOT NULL,
            travel_class TEXT NOT NULL,
            total_fare REAL NOT NULL,
            status TEXT DEFAULT 'CONFIRMED',
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (train_id) REFERENCES trains(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS passengers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            berth TEXT,
            seat_number INTEGER,
            FOREIGN KEY (booking_id) REFERENCES bookings(id)
        )
    """)

        # Stations for each train
    conn.execute("""
        CREATE TABLE IF NOT EXISTS train_stations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            train_id INTEGER NOT NULL,
            station_name TEXT NOT NULL,
            arrival TEXT,
            departure TEXT,
            stop_order INTEGER NOT NULL,
            distance_from_source REAL DEFAULT 0,
            FOREIGN KEY (train_id) REFERENCES trains(id)
        )
    """)

    # Current running status of a train for a particular journey date
    conn.execute("""
        CREATE TABLE IF NOT EXISTS running_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            train_id INTEGER NOT NULL,
            journey_date TEXT NOT NULL,
            current_station_id INTEGER,
            status TEXT NOT NULL,
            delay_minutes INTEGER DEFAULT 0,
            last_updated TEXT NOT NULL,
            FOREIGN KEY (train_id) REFERENCES trains(id),
            FOREIGN KEY (current_station_id) REFERENCES train_stations(id),
            UNIQUE(train_id, journey_date)
        )
    """)

    # Keep older databases compatible with the fare model.
    train_columns = {row[1] for row in conn.execute("PRAGMA table_info(trains)").fetchall()}
    if "train_type" not in train_columns:
        conn.execute("ALTER TABLE trains ADD COLUMN train_type TEXT DEFAULT 'NORMAL'")

    station_columns = {row[1] for row in conn.execute("PRAGMA table_info(train_stations)").fetchall()}
    if "distance_from_source" not in station_columns:
        conn.execute("ALTER TABLE train_stations ADD COLUMN distance_from_source REAL DEFAULT 0")

    # Create default admin
    conn.execute("""
        INSERT OR IGNORE INTO admins (username, password)
        VALUES (?, ?)
    """, ("admin", "admin123"))

    sample_trains = [
        (
            "12951",
            "Mumbai Rajdhani",
            "Mumbai Central",
            "New Delhi",
            "17:00",
            "08:35",
            "15h 35m",
            64,
            48,
            24,
            10,
            "RAJDHANI"
        ),
        (
            "12123",
            "Deccan Queen",
            "Mumbai Central",
            "Pune",
            "07:15",
            "10:25",
            "3h 10m",
            80,
            48,
            24,
            10,
            "SUPERFAST"
        ),
        (
            "12953",
            "August Kranti Rajdhani",
            "Mumbai Central",
            "New Delhi",
            "17:10",
            "10:55",
            "17h 45m",
            64,
            48,
            24,
            10,
            "RAJDHANI"
        ),
        (
            "12009",
            "Mumbai Shatabdi",
            "Mumbai Central",
            "Ahmedabad",
            "06:25",
            "13:10",
            "6h 45m",
            80,
            48,
            24,
            10,
            "SHATABDI"
        )
    ]

    for train in sample_trains:
        conn.execute("""
            INSERT OR IGNORE INTO trains (
                train_number,
                train_name,
                source,
                destination,
                departure,
                arrival,
                duration,
                sleeper_seats,
                ac3_seats,
                ac2_seats,
                ac1_seats,
                train_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, train)

            # Add stations for sample trains

        station_data = {

            "12951": [
                ("Mumbai Central", "17:00", "17:00"),
                ("Borivali", "17:35", "17:38"),
                ("Surat", "20:15", "20:20"),
                ("Vadodara", "22:00", "22:05"),
                ("Ratlam", "02:05", "02:10"),
                ("Kota", "05:10", "05:15"),
                ("New Delhi", "08:35", "08:35")
            ],

            "12123": [
                ("Mumbai Central", "07:15", "07:15"),
                ("Dadar", "07:25", "07:27"),
                ("Lonavala", "09:05", "09:07"),
                ("Pune", "10:25", "10:25")
            ],

            "12953": [
                ("Mumbai Central", "17:10", "17:10"),
                ("Borivali", "17:45", "17:48"),
                ("Surat", "20:30", "20:35"),
                ("Vadodara", "22:15", "22:20"),
                ("Ratlam", "02:25", "02:30"),
                ("Kota", "05:30", "05:35"),
                ("New Delhi", "10:55", "10:55")
            ],

            "12009": [
                ("Mumbai Central", "06:25", "06:25"),
                ("Borivali", "06:55", "06:57"),
                ("Vapi", "08:20", "08:22"),
                ("Surat", "09:30", "09:32"),
                ("Vadodara", "10:40", "10:42"),
                ("Ahmedabad", "13:10", "13:10")
            ]
        }

        for train_number, stations in station_data.items():

            train = conn.execute(
                """
                SELECT id
                FROM trains
                WHERE train_number = ?
                """,
                (train_number,)
            ).fetchone()

            if not train:
                continue

            train_id = train["id"]

            # Don't insert duplicate stations
            existing = conn.execute(
                """
                SELECT COUNT(*)
                FROM train_stations
                WHERE train_id = ?
                """,
                (train_id,)
            ).fetchone()[0]

            if existing == 0:

                for order, station in enumerate(stations, start=1):

                    station_name, arrival, departure = station

                    conn.execute(
                        """
                        INSERT INTO train_stations (
                            train_id,
                            station_name,
                            arrival,
                            departure,
                            stop_order,
                            distance_from_source
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            train_id,
                            station_name,
                            arrival,
                            departure,
                            order,
                            0
                        )
                    )

    # Populate the prototype station distances used by the fare engine.
    prototype_distances = {
        "12951": {"Mumbai Central": 0, "Borivali": 30, "Surat": 263, "Vadodara": 392, "Ratlam": 653, "Kota": 920, "New Delhi": 1384},
        "12123": {"Mumbai Central": 0, "Dadar": 10, "Lonavala": 128, "Pune": 192},
        "12953": {"Mumbai Central": 0, "Borivali": 30, "Surat": 263, "Vadodara": 392, "Ratlam": 653, "Kota": 920, "New Delhi": 1384},
        "12009": {"Mumbai Central": 0, "Borivali": 30, "Vapi": 170, "Surat": 263, "Vadodara": 392, "Ahmedabad": 491},
        "12954": {"Mumbai Central": 0, "Pune": 192},
    }
    for train_number, distances in prototype_distances.items():
        train_row = conn.execute(
            "SELECT id FROM trains WHERE train_number = ?",
            (train_number,)
        ).fetchone()
        if train_row:
            for station_name, distance in distances.items():
                conn.execute(
                    """
                    UPDATE train_stations
                    SET distance_from_source = ?
                    WHERE train_id = ? AND station_name = ?
                    """,
                    (distance, train_row["id"], station_name)
                )

    # Ensure the built-in prototype trains have the intended fare types even
    # when they already existed before the fare model was added.
    train_type_updates = {
        "12951": "RAJDHANI",
        "12123": "SUPERFAST",
        "12953": "RAJDHANI",
        "12009": "SHATABDI",
        "12954": "SUPERFAST",
        "12345": "NORMAL",
    }
    for train_number, train_type in train_type_updates.items():
        conn.execute(
            "UPDATE trains SET train_type = ? WHERE train_number = ?",
            (train_type, train_number)
        )

    conn.commit()
    conn.close()


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/trains")
def trains():
    source = (request.args.get("from") or "").strip()
    destination = (request.args.get("to") or "").strip()
    journey_date = request.args.get("date") or ""
    travel_class = request.args.get("class") or "all"

    if not source or not destination:
        return redirect(url_for("home"))

    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM trains
        WHERE LOWER(TRIM(source)) = LOWER(TRIM(?))
          AND LOWER(TRIM(destination)) = LOWER(TRIM(?))
        ORDER BY departure
        """,
        (source, destination)
    ).fetchall()

    train_results = []
    for train in rows:
        fare_data = get_train_fares(conn, train, source, destination)
        item = dict(train)
        item["journey_distance"] = fare_data["distance"]
        item["fares"] = fare_data["fares"]
        train_results.append(item)

    conn.close()

    return render_template(
        "trains.html",
        trains=train_results,
        journey_date=journey_date,
        travel_class=travel_class,
        source=source,
        destination=destination,
        fares=(train_results[0]["fares"] if train_results else {}),
        train_fares={item["id"]: item["fares"] for item in train_results},
        class_labels=CLASS_LABELS
    )


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()

        try:
            conn.execute(
                """
                INSERT INTO users (name, email, password)
                VALUES (?, ?, ?)
                """,
                (name, email, password)
            )

            conn.commit()
            conn.close()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            conn.close()
            return "Email already registered."

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            """
            SELECT * FROM users
            WHERE email = ? AND password = ?
            """,
            (email, password)
        ).fetchone()

        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]

            return redirect(url_for("home"))

        return "Invalid email or password."

    return render_template("login.html")


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


@app.route("/book/<int:train_id>")
def book(train_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    journey_date = request.args.get("date") or ""
    travel_class = request.args.get("class") or "all"

    conn = get_db()
    train = conn.execute(
        "SELECT * FROM trains WHERE id = ?",
        (train_id,)
    ).fetchone()

    if not train:
        conn.close()
        return "Train not found.", 404

    fare_data = get_train_fares(conn, train)
    conn.close()

    return render_template(
        "booking.html",
        train=train,
        journey_date=journey_date,
        travel_class=travel_class,
        fares=fare_data["fares"],
        journey_distance=fare_data["distance"],
        class_labels=CLASS_LABELS
    )


@app.route("/confirm-booking", methods=["POST"])
def confirm_booking():

    if not session.get("user_id"):
        return redirect(url_for("login"))

    train_id = request.form["train_id"]
    journey_date = request.form["journey_date"]
    travel_class = request.form["travel_class"]

    passenger_name = request.form["passenger_name"]
    passenger_age = request.form["passenger_age"]
    passenger_gender = request.form["passenger_gender"]

    # Seat columns for each class
    seat_columns = {
        "sleeper": "sleeper_seats",
        "3A": "ac3_seats",
        "2A": "ac2_seats",
        "1A": "ac1_seats"
    }

    seat_column = seat_columns.get(travel_class)

    if not seat_column:
        return "Invalid travel class."

    conn = get_db()

    # Get train
    train = conn.execute(
        "SELECT * FROM trains WHERE id = ?",
        (train_id,)
    ).fetchone()

    if not train:
        conn.close()
        return "Train not found."

    fare_data = get_train_fares(conn, train)
    journey_distance = fare_data["distance"]

    if journey_distance is None:
        conn.close()
        return "Route distance data is missing."

    fare_class = "SL" if travel_class == "sleeper" else travel_class

    total_fare = calculate_fare(
        journey_distance,
        fare_class,
        train["train_type"] or "NORMAL"
    )

    # Current remaining seats
    available_seats = train[seat_column]

    if available_seats <= 0:
        conn.close()
        return "No seats available in this class."

    # -------------------------------------------------
    # Find all currently occupied seats
    # -------------------------------------------------

    used_seats = conn.execute(
        """
        SELECT passengers.seat_number
        FROM passengers
        JOIN bookings
            ON passengers.booking_id = bookings.id
        WHERE bookings.train_id = ?
        AND bookings.travel_class = ?
        AND bookings.status = 'CONFIRMED'
        """,
        (train_id, travel_class)
    ).fetchall()

    used_seat_numbers = {
        row["seat_number"]
        for row in used_seats
        if row["seat_number"] is not None
    }

    # -------------------------------------------------
    # Determine total capacity
    #
    # Current remaining seats + currently occupied seats
    # = total capacity
    # -------------------------------------------------

    total_capacity = available_seats + len(used_seat_numbers)

    # Find the lowest free seat
    seat_number = None

    for number in range(1, total_capacity + 1):

        if number not in used_seat_numbers:
            seat_number = number
            break

    if seat_number is None:
        conn.close()
        return "No seats available."

    # -------------------------------------------------
    # Generate unique PNR
    # -------------------------------------------------

    import random

    while True:

        pnr = str(random.randint(1000000000, 9999999999))

        existing_pnr = conn.execute(
            """
            SELECT id
            FROM bookings
            WHERE pnr = ?
            """,
            (pnr,)
        ).fetchone()

        if not existing_pnr:
            break

    # -------------------------------------------------
    # Create booking
    # -------------------------------------------------

    cursor = conn.execute(
        """
        INSERT INTO bookings (
            pnr,
            user_id,
            train_id,
            journey_date,
            travel_class,
            total_fare,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pnr,
            session["user_id"],
            train_id,
            journey_date,
            travel_class,
            total_fare,
            "CONFIRMED"
        )
    )

    booking_id = cursor.lastrowid

    # -------------------------------------------------
    # Add passenger
    # -------------------------------------------------

    conn.execute(
        """
        INSERT INTO passengers (
            booking_id,
            name,
            age,
            gender,
            berth,
            seat_number
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            booking_id,
            passenger_name,
            passenger_age,
            passenger_gender,
            "Auto",
            seat_number
        )
    )

    # -------------------------------------------------
    # Decrease available seat count
    # -------------------------------------------------

    conn.execute(
        f"""
        UPDATE trains
        SET {seat_column} = {seat_column} - 1
        WHERE id = ?
        """,
        (train_id,)
    )

    conn.commit()
    conn.close()

    return redirect(
        url_for(
            "ticket",
            booking_id=booking_id
        )
    )
@app.route("/ticket/<int:booking_id>")
def ticket(booking_id):

    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()

    booking = conn.execute(
        """
        SELECT
            bookings.*,
            trains.train_number,
            trains.train_name,
            trains.source,
            trains.destination,
            trains.departure,
            trains.arrival,
            passengers.name,
            passengers.age,
            passengers.gender,
            passengers.berth,
            passengers.seat_number
        FROM bookings
        JOIN trains
            ON bookings.train_id = trains.id
        JOIN passengers
            ON bookings.id = passengers.booking_id
        WHERE bookings.id = ?
        AND bookings.user_id = ?
        """,
        (booking_id, session["user_id"])
    ).fetchone()

    conn.close()

    if not booking:
        return "Booking not found."

    return render_template(
        "ticket.html",
        booking=booking
    )

@app.route("/my-bookings")
def my_bookings():

    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()

    bookings = conn.execute(
        """
        SELECT
            bookings.id,
            bookings.pnr,
            bookings.journey_date,
            bookings.travel_class,
            bookings.total_fare,
            bookings.status,

            trains.train_number,
            trains.train_name,
            trains.source,
            trains.destination,
            trains.departure,
            trains.arrival,

            passengers.name AS passenger_name,
            passengers.age,
            passengers.gender,
            passengers.seat_number

        FROM bookings

        JOIN trains
            ON bookings.train_id = trains.id

        JOIN passengers
            ON bookings.id = passengers.booking_id

        WHERE bookings.user_id = ?

        ORDER BY bookings.id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "my_bookings.html",
        bookings=bookings
    )


@app.route("/cancel-booking/<int:booking_id>", methods=["POST"])
def cancel_booking(booking_id):

    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()

    booking = conn.execute(
        """
        SELECT *
        FROM bookings
        WHERE id = ?
        AND user_id = ?
        """,
        (booking_id, session["user_id"])
    ).fetchone()

    if not booking:
        conn.close()
        return "Booking not found."

    if booking["status"] == "CANCELLED":
        conn.close()
        return redirect(url_for("my_bookings"))

    # Determine which seat column must be restored
    seat_columns = {
        "sleeper": "sleeper_seats",
        "3A": "ac3_seats",
        "2A": "ac2_seats",
        "1A": "ac1_seats"
    }

    seat_column = seat_columns.get(booking["travel_class"])

    if not seat_column:
        conn.close()
        return "Invalid travel class."

    # Restore one seat
    conn.execute(
        f"""
        UPDATE trains
        SET {seat_column} = {seat_column} + 1
        WHERE id = ?
        """,
        (booking["train_id"],)
    )

    # Cancel booking
    conn.execute(
        """
        UPDATE bookings
        SET status = 'CANCELLED'
        WHERE id = ?
        """,
        (booking_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("my_bookings"))

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()

        admin = conn.execute(
            """
            SELECT *
            FROM admins
            WHERE username = ?
            AND password = ?
            """,
            (username, password)
        ).fetchone()

        conn.close()

        if admin:
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]

            return redirect(url_for("admin_dashboard"))

        return "Invalid admin username or password."

    return render_template("admin_login.html")

@app.route("/admin/dashboard")
def admin_dashboard():

    if not session.get("admin_id"):
        return redirect(url_for("admin_login"))

    from datetime import date

    journey_date = request.args.get("date") or date.today().isoformat()
    conn = get_db()

    trains = conn.execute(
        "SELECT * FROM trains ORDER BY train_number"
    ).fetchall()

    total_trains = len(trains)
    total_bookings = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    confirmed_bookings = conn.execute(
        "SELECT COUNT(*) FROM bookings WHERE status = 'CONFIRMED'"
    ).fetchone()[0]
    cancelled_bookings = conn.execute(
        "SELECT COUNT(*) FROM bookings WHERE status = 'CANCELLED'"
    ).fetchone()[0]

    operations = []
    counts = {"RUNNING": 0, "DELAYED": 0, "CANCELLED": 0, "ARRIVED": 0, "NOT_STARTED": 0, "AT_STATION": 0}

    for train in trains:
        stations = conn.execute(
            "SELECT * FROM train_stations WHERE train_id = ? ORDER BY stop_order",
            (train["id"],)
        ).fetchall()
        status = conn.execute(
            "SELECT * FROM running_status WHERE train_id = ? AND journey_date = ?",
            (train["id"], journey_date)
        ).fetchone()

        if status and status["status"] == "CANCELLED":
            position = {"state": "CANCELLED", "current_station": None, "next_station": None, "progress": 0, "eta": None}
        else:
            delay = (status["delay_minutes"] or 0) if status else 0
            position = calculate_train_position(stations, journey_date, delay)
            if status and status["status"] == "ARRIVED" and stations:
                position["state"] = "ARRIVED"
                position["current_station"] = stations[-1]
                position["next_station"] = None
                position["progress"] = 100

        state = position["state"]
        if status and status["status"] == "DELAYED" and state not in ("CANCELLED", "ARRIVED"):
            display_state = "DELAYED"
        else:
            display_state = state
        counts[display_state] = counts.get(display_state, 0) + 1

        current_name = position["current_station"]["station_name"] if position.get("current_station") else "—"
        next_name = position["next_station"]["station_name"] if position.get("next_station") else "—"

        operations.append({
            "train": train,
            "status": status,
            "position": position,
            "display_state": display_state,
            "current_name": current_name,
            "next_name": next_name,
            "delay": (status["delay_minutes"] or 0) if status else 0,
            "journey_date": journey_date
        })

    conn.close()

    return render_template(
        "admin_dashboard.html",
        trains=trains,
        total_trains=total_trains,
        total_bookings=total_bookings,
        confirmed_bookings=confirmed_bookings,
        cancelled_bookings=cancelled_bookings,
        operations=operations,
        counts=counts,
        journey_date=journey_date
    )

@app.route("/admin/add-train", methods=["GET", "POST"])
def admin_add_train():

    if not session.get("admin_id"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":

        train_number = request.form["train_number"]
        train_name = request.form["train_name"]
        source = request.form["source"]
        destination = request.form["destination"]
        departure = request.form["departure"]
        arrival = request.form["arrival"]
        duration = request.form["duration"]
        train_type = request.form.get("train_type") or "NORMAL"

        sleeper_seats = request.form["sleeper_seats"]
        ac3_seats = request.form["ac3_seats"]
        ac2_seats = request.form["ac2_seats"]
        ac1_seats = request.form["ac1_seats"]

        conn = get_db()

        try:

            conn.execute(
                """
                INSERT INTO trains (
                    train_number,
                    train_name,
                    source,
                    destination,
                    departure,
                    arrival,
                    duration,
                    sleeper_seats,
                    ac3_seats,
                    ac2_seats,
                    ac1_seats,
                    train_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    train_number,
                    train_name,
                    source,
                    destination,
                    departure,
                    arrival,
                    duration,
                    sleeper_seats,
                    ac3_seats,
                    ac2_seats,
                    ac1_seats,
                    train_type
                )
            )

            conn.commit()
            conn.close()

            return redirect(url_for("admin_dashboard"))

        except sqlite3.IntegrityError:

            conn.close()

            return "Train number already exists."

    return render_template("admin_add_train.html")

@app.route("/admin/edit-train/<int:train_id>", methods=["GET", "POST"])
def admin_edit_train(train_id):

    if not session.get("admin_id"):
        return redirect(url_for("admin_login"))

    conn = get_db()

    train = conn.execute(
        "SELECT * FROM trains WHERE id = ?",
        (train_id,)
    ).fetchone()

    if not train:
        conn.close()
        return "Train not found."

    if request.method == "POST":

        train_number = request.form["train_number"]
        train_name = request.form["train_name"]
        source = request.form["source"]
        destination = request.form["destination"]
        departure = request.form["departure"]
        arrival = request.form["arrival"]
        duration = request.form["duration"]
        train_type = request.form.get("train_type") or "NORMAL"

        sleeper_seats = request.form["sleeper_seats"]
        ac3_seats = request.form["ac3_seats"]
        ac2_seats = request.form["ac2_seats"]
        ac1_seats = request.form["ac1_seats"]

        try:

            conn.execute(
                """
                UPDATE trains
                SET
                    train_number = ?,
                    train_name = ?,
                    source = ?,
                    destination = ?,
                    departure = ?,
                    arrival = ?,
                    duration = ?,
                    sleeper_seats = ?,
                    ac3_seats = ?,
                    ac2_seats = ?,
                    ac1_seats = ?,
                    train_type = ?
                WHERE id = ?
                """,
                (
                    train_number,
                    train_name,
                    source,
                    destination,
                    departure,
                    arrival,
                    duration,
                    sleeper_seats,
                    ac3_seats,
                    ac2_seats,
                    ac1_seats,
                    train_type,
                    train_id
                )
            )

            conn.commit()
            conn.close()

            return redirect(url_for("admin_dashboard"))

        except sqlite3.IntegrityError:

            conn.close()

            return "Train number already exists."

    conn.close()

    return render_template(
        "admin_edit_train.html",
        train=train
    )

@app.route("/admin/delete-train/<int:train_id>")
def admin_delete_train(train_id):

    if not session.get("admin_id"):
        return redirect(url_for("admin_login"))

    conn = get_db()

    train = conn.execute(
        "SELECT * FROM trains WHERE id = ?",
        (train_id,)
    ).fetchone()

    if not train:
        conn.close()
        return "Train not found."

    # Check whether this train has bookings
    bookings = conn.execute(
        """
        SELECT COUNT(*)
        FROM bookings
        WHERE train_id = ?
        """,
        (train_id,)
    ).fetchone()[0]

    if bookings > 0:
        conn.close()
        return "Cannot delete this train because bookings already exist."

    conn.execute(
        "DELETE FROM trains WHERE id = ?",
        (train_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/logout")
def admin_logout():

    session.pop("admin_id", None)
    session.pop("admin_username", None)

    return redirect(url_for("admin_login"))

from datetime import datetime, timedelta


def calculate_train_position(stations, journey_date, delay_minutes=0):
    """
    Calculate the simulated train position from timetable + current time.
    """

    if not stations:
        return {
            "state": "NOT_AVAILABLE",
            "current_station": None,
            "next_station": None,
            "progress": 0,
            "eta": None
        }

    # Build real datetime values for every station.
    timetable = []

    base_date = datetime.strptime(
        journey_date,
        "%Y-%m-%d"
    ).date()

    previous_time = None
    current_day = base_date

    for station in stations:

        arrival_text = station["arrival"]
        departure_text = station["departure"]

        arrival_time = datetime.strptime(
            arrival_text,
            "%H:%M"
        ).time()

        departure_time = datetime.strptime(
            departure_text,
            "%H:%M"
        ).time()

        # Detect crossing midnight.
        if previous_time is not None:
            if arrival_time < previous_time:
                current_day += timedelta(days=1)

        arrival_dt = datetime.combine(
            current_day,
            arrival_time
        )

        departure_dt = datetime.combine(
            current_day,
            departure_time
        )

        # Departure can also cross midnight.
        if departure_dt < arrival_dt:
            departure_dt += timedelta(days=1)

        timetable.append({
            "station": station,
            "arrival": arrival_dt,
            "departure": departure_dt
        })

        previous_time = departure_time

    # Apply delay to the whole journey.
    delay = timedelta(minutes=delay_minutes)

    for item in timetable:
        item["arrival"] += delay
        item["departure"] += delay

    now = datetime.now()

    first_departure = timetable[0]["departure"]
    final_arrival = timetable[-1]["arrival"]

    # Before train starts
    if now < first_departure:

        return {
            "state": "NOT_STARTED",
            "current_station": None,
            "next_station": timetable[0]["station"],
            "progress": 0,
            "eta": first_departure.strftime("%H:%M")
        }

    # Train has reached destination
    if now >= final_arrival:

        return {
            "state": "ARRIVED",
            "current_station": timetable[-1]["station"],
            "next_station": None,
            "progress": 100,
            "eta": final_arrival.strftime("%H:%M")
        }

    # Find current section of journey.
    for i in range(len(timetable) - 1):

        current = timetable[i]
        next_stop = timetable[i + 1]

        # Train is currently at this station.
        if (
            current["arrival"]
            <= now
            <= current["departure"]
        ):

            return {
                "state": "AT_STATION",
                "current_station": current["station"],
                "next_station": next_stop["station"],
                "progress": 0,
                "eta": next_stop["arrival"].strftime("%H:%M")
            }

        # Train is travelling towards next station.
        if (
            current["departure"]
            <= now
            < next_stop["arrival"]
        ):

            total_seconds = (
                next_stop["arrival"]
                - current["departure"]
            ).total_seconds()

            elapsed_seconds = (
                now
                - current["departure"]
            ).total_seconds()

            progress = (
                elapsed_seconds /
                total_seconds
            ) * 100

            progress = max(
                0,
                min(100, progress)
            )

            return {
                "state": "RUNNING",
                "current_station": current["station"],
                "next_station": next_stop["station"],
                "progress": round(progress),
                "eta": next_stop["arrival"].strftime("%H:%M")
            }

    return {
        "state": "UNKNOWN",
        "current_station": None,
        "next_station": None,
        "progress": 0,
        "eta": None
    }

@app.route("/running-status", methods=["GET", "POST"])
def running_status():

    train = None
    stations = []
    status = None
    position = None

    if request.method == "POST":

        train_number = request.form["train_number"]
        journey_date = request.form["journey_date"]

        conn = get_db()

        train = conn.execute(
            """
            SELECT *
            FROM trains
            WHERE train_number = ?
            """,
            (train_number,)
        ).fetchone()

        if not train:
            conn.close()
            return "Train not found."

        stations = conn.execute(
            """
            SELECT *
            FROM train_stations
            WHERE train_id = ?
            ORDER BY stop_order
            """,
            (train["id"],)
        ).fetchall()

        status = conn.execute(
            """
            SELECT *
            FROM running_status
            WHERE train_id = ?
            AND journey_date = ?
            """,
            (
                train["id"],
                journey_date
            )
        ).fetchone()

        conn.close()

        # No manual status means normal timetable operation.
        if not status:

            position = calculate_train_position(
                stations,
                journey_date,
                0
            )

        else:

            # Cancelled is controlled by admin.
            if status["status"] == "CANCELLED":

                position = {
                    "state": "CANCELLED",
                    "current_station": None,
                    "next_station": None,
                    "progress": 0,
                    "eta": None
                }

            else:

                position = calculate_train_position(
                    stations,
                    journey_date,
                    status["delay_minutes"] or 0
                )

                # If admin explicitly marked ARRIVED,
                # respect that.
                if status["status"] == "ARRIVED":

                    position["state"] = "ARRIVED"
                    position["current_station"] = stations[-1]
                    position["next_station"] = None
                    position["progress"] = 100

    return render_template(
        "running_status.html",
        train=train,
        stations=stations,
        status=status,
        position=position
    )

@app.route("/admin/running-status", methods=["GET", "POST"])
def admin_running_status():

    if not session.get("admin_id"):
        return redirect(url_for("admin_login"))

    from datetime import date
    journey_date = request.args.get("date") or request.form.get("journey_date") or date.today().isoformat()
    conn = get_db()

    if request.method == "POST":
        train_id = request.form["train_id"]
        journey_date = request.form["journey_date"]
        current_station_id = request.form.get("current_station_id") or None
        status_value = request.form["status"]
        delay_minutes = int(request.form.get("delay_minutes") or 0)

        conn.execute(
            """
            INSERT INTO running_status (
                train_id, journey_date, current_station_id, status,
                delay_minutes, last_updated
            )
            VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(train_id, journey_date)
            DO UPDATE SET
                current_station_id = excluded.current_station_id,
                status = excluded.status,
                delay_minutes = excluded.delay_minutes,
                last_updated = excluded.last_updated
            """,
            (train_id, journey_date, current_station_id, status_value, delay_minutes)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("admin_running_status", date=journey_date))

    trains = conn.execute("SELECT * FROM trains ORDER BY train_number").fetchall()
    rows = []

    for train in trains:
        stations = conn.execute(
            "SELECT * FROM train_stations WHERE train_id = ? ORDER BY stop_order",
            (train["id"],)
        ).fetchall()
        status = conn.execute(
            "SELECT * FROM running_status WHERE train_id = ? AND journey_date = ?",
            (train["id"], journey_date)
        ).fetchone()

        if status and status["status"] == "CANCELLED":
            position = {"state": "CANCELLED", "current_station": None, "next_station": None, "progress": 0, "eta": None}
        else:
            delay = (status["delay_minutes"] or 0) if status else 0
            position = calculate_train_position(stations, journey_date, delay)
            if status and status["status"] == "ARRIVED" and stations:
                position["state"] = "ARRIVED"
                position["current_station"] = stations[-1]
                position["next_station"] = None
                position["progress"] = 100

        display_state = "DELAYED" if status and status["status"] == "DELAYED" and position["state"] not in ("CANCELLED", "ARRIVED") else position["state"]
        rows.append({"train": train, "stations": stations, "status": status, "position": position, "display_state": display_state})

    conn.close()
    return render_template("admin_running_status.html", rows=rows, journey_date=journey_date)

@app.route("/admin/train-stations/<int:train_id>")
def admin_train_stations(train_id):

    if not session.get("admin_id"):
        return {"error": "Unauthorized"}, 401

    conn = get_db()

    stations = conn.execute(
        """
        SELECT id, station_name, stop_order, distance_from_source
        FROM train_stations
        WHERE train_id = ?
        ORDER BY stop_order
        """,
        (train_id,)
    ).fetchall()

    conn.close()

    return [
        {
            "id": station["id"],
            "station_name": station["station_name"],
            "stop_order": station["stop_order"],
            "distance_from_source": station["distance_from_source"]
        }
        for station in stations
    ]

@app.route("/train-route/<int:train_id>")
def train_route(train_id):
    conn = get_db()
    train = conn.execute(
        "SELECT * FROM trains WHERE id = ?",
        (train_id,)
    ).fetchone()
    stations = conn.execute(
        "SELECT * FROM train_stations WHERE train_id = ? ORDER BY stop_order",
        (train_id,)
    ).fetchall() if train else []
    if not train:
        conn.close()
        return "Train not found.", 404

    fare_data = get_train_fares(conn, train)
    conn.close()

    # Preserve the exact search state so Back to Trains never loses the
    # user's date/class/filter context.
    search_params = {
        "from": request.args.get("from") or train["source"],
        "to": request.args.get("to") or train["destination"],
        "date": request.args.get("date") or "",
        "class": request.args.get("class") or "all"
    }

    return render_template(
        "train_route.html",
        train=train,
        stations=stations,
        search_params=search_params,
        fares=fare_data["fares"],
        journey_distance=fare_data["distance"],
        class_labels=CLASS_LABELS
    )


@app.route("/admin/routes")
def admin_routes():
    if not session.get("admin_id"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    trains = conn.execute("SELECT * FROM trains ORDER BY train_number").fetchall()
    selected_id = request.args.get("train_id", type=int)
    selected_train = None
    stations = []
    if selected_id:
        selected_train = conn.execute("SELECT * FROM trains WHERE id = ?", (selected_id,)).fetchone()
        if selected_train:
            stations = conn.execute("SELECT * FROM train_stations WHERE train_id = ? ORDER BY stop_order", (selected_id,)).fetchall()
    elif trains:
        selected_train = trains[0]
        stations = conn.execute("SELECT * FROM train_stations WHERE train_id = ? ORDER BY stop_order", (selected_train["id"],)).fetchall()
    conn.close()
    return render_template("admin_routes.html", trains=trains, selected_train=selected_train, stations=stations)

@app.route("/admin/bookings")
def admin_bookings():
    if not session.get("admin_id"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    pnr = request.args.get("pnr", "").strip()
    query = """
        SELECT bookings.*, users.name AS user_name, users.email, trains.train_number, trains.train_name, trains.source, trains.destination, passengers.name AS passenger_name, passengers.age, passengers.gender, passengers.seat_number
        FROM bookings
        JOIN users ON bookings.user_id = users.id
        JOIN trains ON bookings.train_id = trains.id
        LEFT JOIN passengers ON bookings.id = passengers.booking_id
    """
    params = ()
    if pnr:
        query += " WHERE bookings.pnr = ?"
        params = (pnr,)
    query += " ORDER BY bookings.id DESC"
    bookings = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("admin_bookings.html", bookings=bookings, pnr=pnr)

@app.route("/pnr-status", methods=["GET", "POST"])
def pnr_status():

    booking = None
    passengers = []

    if request.method == "POST":

        pnr = request.form["pnr"].strip()

        conn = get_db()

        booking = conn.execute(
            """
            SELECT
                bookings.*,
                trains.train_number,
                trains.train_name,
                trains.source,
                trains.destination
            FROM bookings
            JOIN trains
                ON bookings.train_id = trains.id
            WHERE bookings.pnr = ?
            """,
            (pnr,)
        ).fetchone()

        if booking:
            passengers = conn.execute(
                """
                SELECT *
                FROM passengers
                WHERE booking_id = ?
                ORDER BY id
                """,
                (booking["id"],)
            ).fetchall()

        conn.close()

    return render_template(
        "pnr_status.html",
        booking=booking,
        passengers=passengers
    )


@app.route("/admin/routes/add", methods=["POST"])
def admin_route_add():
    if not session.get("admin_id"):
        return redirect(url_for("admin_login"))

    train_id = request.form.get("train_id", type=int)
    station_name = request.form.get("station_name", "").strip()
    arrival = request.form.get("arrival") or None
    departure = request.form.get("departure") or None
    stop_order = request.form.get("stop_order", type=int)
    distance_from_source = request.form.get("distance_from_source", type=float)
    if distance_from_source is None:
        distance_from_source = 0

    if not train_id or not station_name or not stop_order or stop_order < 1:
        return "Invalid station details.", 400

    conn = get_db()
    train = conn.execute("SELECT id FROM trains WHERE id = ?", (train_id,)).fetchone()
    if not train:
        conn.close()
        return "Train not found.", 404

    count = conn.execute(
        "SELECT COUNT(*) FROM train_stations WHERE train_id = ?", (train_id,)
    ).fetchone()[0]
    stop_order = min(stop_order, count + 1)

    # Make room for the new stop.
    conn.execute(
        "UPDATE train_stations SET stop_order = stop_order + 1 WHERE train_id = ? AND stop_order >= ?",
        (train_id, stop_order)
    )
    conn.execute(
        """INSERT INTO train_stations
           (train_id, station_name, arrival, departure, stop_order, distance_from_source)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (train_id, station_name, arrival, departure, stop_order, distance_from_source)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_routes", train_id=train_id))


@app.route("/admin/routes/edit/<int:station_id>", methods=["GET", "POST"])
def admin_route_edit(station_id):
    if not session.get("admin_id"):
        return redirect(url_for("admin_login"))

    conn = get_db()
    station = conn.execute(
        "SELECT * FROM train_stations WHERE id = ?", (station_id,)
    ).fetchone()

    if not station:
        conn.close()
        return "Station not found.", 404

    train = conn.execute(
        "SELECT * FROM trains WHERE id = ?", (station["train_id"],)
    ).fetchone()

    if request.method == "POST":
        station_name = request.form.get("station_name", "").strip()
        arrival = request.form.get("arrival") or None
        departure = request.form.get("departure") or None
        new_order = request.form.get("stop_order", type=int)
        distance_from_source = request.form.get("distance_from_source", type=float)
        if distance_from_source is None:
            distance_from_source = 0

        if not station_name or not new_order or new_order < 1:
            conn.close()
            return "Invalid station details.", 400

        train_id = station["train_id"]
        max_order = conn.execute(
            "SELECT COUNT(*) FROM train_stations WHERE train_id = ?", (train_id,)
        ).fetchone()[0]
        new_order = min(new_order, max_order)
        old_order = station["stop_order"]

        if new_order != old_order:
            if new_order < old_order:
                conn.execute(
                    """UPDATE train_stations
                       SET stop_order = stop_order + 1
                       WHERE train_id = ? AND stop_order >= ? AND stop_order < ? AND id != ?""",
                    (train_id, new_order, old_order, station_id)
                )
            else:
                conn.execute(
                    """UPDATE train_stations
                       SET stop_order = stop_order - 1
                       WHERE train_id = ? AND stop_order <= ? AND stop_order > ? AND id != ?""",
                    (train_id, new_order, old_order, station_id)
                )

        conn.execute(
            """UPDATE train_stations
               SET station_name = ?, arrival = ?, departure = ?, stop_order = ?
               WHERE id = ?""",
            (station_name, arrival, departure, new_order, station_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("admin_routes", train_id=train_id))

    conn.close()
    return render_template("admin_route_edit.html", station=station, train=train)


@app.route("/admin/routes/delete/<int:station_id>")
def admin_route_delete(station_id):
    if not session.get("admin_id"):
        return redirect(url_for("admin_login"))

    conn = get_db()
    station = conn.execute(
        "SELECT train_id, stop_order FROM train_stations WHERE id = ?", (station_id,)
    ).fetchone()
    if not station:
        conn.close()
        return "Station not found.", 404

    train_id = station["train_id"]
    deleted_order = station["stop_order"]

    conn.execute("DELETE FROM train_stations WHERE id = ?", (station_id,))
    conn.execute(
        "UPDATE train_stations SET stop_order = stop_order - 1 WHERE train_id = ? AND stop_order > ?",
        (train_id, deleted_order)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_routes", train_id=train_id))


def start_app():
    init_db()
    app.run(debug=True)


if __name__ == "__main__":
    start_app()
