# Train Ticket Booking System (TTBS)

TTBS is a Flask and SQLite prototype for searching trains, booking a seat, viewing
ticket and PNR details, and checking a train's timetable-based running status.
It also includes an administration area for managing trains, routes, bookings,
and running-status overrides.

This is a local demonstration project. It does not connect to railway systems,
live train tracking, payment providers, or real ticket inventory.

## Features

- Search trains by their listed source and destination.
- View train routes, station timings, and prototype fares for Sleeper, 3A, 2A,
  and 1A classes.
- Register and sign in as a passenger.
- Make and cancel prototype bookings; view bookings, tickets, and PNR status.
- Calculate a train's running position from its timetable and journey date.
- Sign in as an administrator to manage trains, stations, bookings, and running
  status.
- Store application data in a local SQLite database.

## Requirements

- Python 3
- `pip`

The Python dependencies are listed in [`requirements.txt`](requirements.txt).

## Setup and run

Run these commands from the project root (the directory containing `app.py`).

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

If PowerShell blocks virtual-environment activation, either allow scripts for
the current PowerShell process or run the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

### macOS and Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

Open [http://127.0.0.1:5000/](http://127.0.0.1:5000/) in your browser. Stop the
development server with **Ctrl+C** in the terminal.

Run `python app.py` from the project root: the startup code initializes the
database before starting Flask. Starting the app from another directory can
create or look for `database.db` in the wrong location.

## First run and database

On startup, the application creates `database.db` in the current working
directory if it does not already exist. It creates the required tables and adds
the built-in demonstration trains, stations, and administrator when they are
missing. Startup also applies the fare-related schema additions to older
databases. Existing records are not intentionally replaced by the sample-data
inserts.

The database contains passenger accounts, bookings, train and station data, and
running-status records. Keep a separate backup before replacing, moving, or
deleting it. Database files and backups are ignored by Git; they are local
application data, not source files.

## Accounts

Create a passenger account from the **Register** link, then sign in to book or
manage tickets.

The local demonstration administrator is:

| Field | Value |
| --- | --- |
| Username | `admin` |
| Password | `admin123` |
| Login page | [http://127.0.0.1:5000/admin/login](http://127.0.0.1:5000/admin/login) |

The application inserts this account during database initialization when it
does not already exist. These are publicly known demo credentials; do not expose
the app or its data to other users with this account.

## Pages

| Page | Path | Purpose |
| --- | --- | --- |
| Home and train search | `/` | Search listed trains by source and destination |
| Search results | `/trains` | View matching trains, fares, and route links |
| Register | `/register` | Create a passenger account |
| Passenger login | `/login` | Sign in to book and manage tickets |
| My bookings | `/my-bookings` | View or cancel your bookings |
| Ticket | `/ticket/<booking_id>` | View a booking's ticket |
| PNR status | `/pnr-status` | Look up a TTBS booking by PNR |
| Running status | `/running-status` | Check timetable-based train status |
| Train route | `/train-route/<train_id>` | View a train's route and station timings |
| Admin login | `/admin/login` | Open the administrator sign-in page |
| Admin dashboard | `/admin/dashboard` | Overview and train management |
| Admin routes | `/admin/routes` | Manage a train's station sequence and timings |
| Admin bookings | `/admin/bookings` | Search and review bookings |
| Admin running status | `/admin/running-status` | Set status and delay overrides |

## Fares and running status

Fares are illustrative prototype calculations in [`fare_engine.py`](fare_engine.py).
They use distance, travel-class multipliers, and a train-category multiplier;
they are not official railway fares. The available categories are `NORMAL`,
`EXPRESS`, `SUPERFAST`, `RAJDHANI`, and `SHATABDI`. Unknown or empty train
categories use the `NORMAL` multiplier.

Running status is calculated from the configured station timetable, journey
date, and the local time on the server. Administrators can provide a status or
delay override. This is a simulation, not a live tracking service.

## Project layout

```text
.
├── app.py                  # Flask routes, database initialization, and app startup
├── fare_engine.py          # Prototype fare and train-category calculations
├── requirements.txt        # Python dependencies
├── static/
│   └── style.css           # Application styles
├── templates/              # Passenger and administrator Jinja/HTML templates
├── database.db             # Local SQLite database created at startup (not tracked)
└── .gitignore              # Excludes local environments, data, and generated files
```

## Security and production limitations

This project is for local development and demonstration only. Before any shared
or production deployment, replace the hard-coded Flask session secret and
default administrator credentials, implement secure password hashing and
appropriate session and request protections, disable Flask debug mode, and use
a production-ready server. The current booking, seat-count, and fare logic is a
prototype and should not be treated as a real reservation or payment system.
