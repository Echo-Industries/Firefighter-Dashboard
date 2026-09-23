import os
import secrets
import sqlite3
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from dotenv import load_dotenv
import requests

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

ERLC_API_KEY = os.getenv("ERLC_SERVER_KEY")
PORT = int(os.getenv("PORT", 5000))
DATABASE_PATH = os.getenv("DATABASE_PATH", "firefighter_dashboard.db")
ROBLOX_CLIENT_ID = os.getenv("ROBLOX_CLIENT_ID")
ROBLOX_CLIENT_SECRET = os.getenv("ROBLOX_CLIENT_SECRET")
ROBLOX_REDIRECT_URI = os.getenv("ROBLOX_REDIRECT_URI")


def get_db():
    database = sqlite3.connect(DATABASE_PATH)
    database.row_factory = sqlite3.Row
    database.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            payload TEXT NOT NULL,
            published_by_id TEXT NOT NULL,
            published_by_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return database


def current_user():
    return session.get("roblox_user")


def login_required(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if not current_user():
            return jsonify({"error": "Sign in with Roblox first."}), 401
        return handler(*args, **kwargs)

    return wrapped


@app.route("/")
def index():
    """Serves the main Station 7 Portal frontend interface."""
    if not current_user():
        return redirect(url_for("login"))
    return render_template("index.html")


@app.route("/login")
def login():
    if current_user():
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/auth/roblox/login")
def roblox_login():
    if not all((ROBLOX_CLIENT_ID, ROBLOX_CLIENT_SECRET, ROBLOX_REDIRECT_URI)):
        return jsonify({
            "error": "Configure ROBLOX_CLIENT_ID, ROBLOX_CLIENT_SECRET, and ROBLOX_REDIRECT_URI in your .env file."
        }), 500

    state = secrets.token_urlsafe(32)
    session["roblox_oauth_state"] = state
    params = {
        "client_id": ROBLOX_CLIENT_ID,
        "redirect_uri": ROBLOX_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid profile",
        "state": state,
    }
    authorization_url = requests.Request(
        "GET", "https://apis.roblox.com/oauth/v1/authorize", params=params
    ).prepare().url
    return redirect(authorization_url)


@app.route("/auth/roblox/callback")
def roblox_callback():
    if request.args.get("state") != session.pop("roblox_oauth_state", None):
        return "Invalid Roblox OAuth state.", 400

    code = request.args.get("code")
    if not code:
        return f"Roblox sign-in failed: {request.args.get('error_description', 'No authorization code returned.')}", 400

    try:
        token_response = requests.post(
            "https://apis.roblox.com/oauth/v1/token",
            data={
                "client_id": ROBLOX_CLIENT_ID,
                "client_secret": ROBLOX_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": ROBLOX_REDIRECT_URI,
            },
            timeout=10,
        )
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]
        user_response = requests.get(
            "https://apis.roblox.com/oauth/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        user_response.raise_for_status()
        user_data = user_response.json()
    except (requests.RequestException, KeyError) as error:
        return f"Roblox sign-in failed: {error}", 502

    user_id = str(user_data["sub"])
    avatar_url = None
    try:
        avatar_response = requests.get(
            "https://thumbnails.roblox.com/v1/users/avatar-headshot",
            params={"userIds": user_id, "size": "150x150", "format": "Png", "isCircular": "false"},
            timeout=10,
        )
        avatar_response.raise_for_status()
        avatar_data = avatar_response.json().get("data", [])
        if avatar_data:
            avatar_url = avatar_data[0].get("imageUrl")
    except (requests.RequestException, ValueError):
        pass

    session["roblox_user"] = {
        "id": user_id,
        "name": user_data.get("preferred_username") or user_data.get("name") or "Roblox user",
        "avatarUrl": avatar_url,
    }
    return redirect(url_for("index"))


@app.route("/auth/logout")
def logout():
    session.pop("roblox_user", None)
    return redirect(url_for("login"))


@app.route("/api/auth/me")
def auth_me():
    return jsonify({"user": current_user()})


@app.route("/api/records", methods=["GET"])
@login_required
def list_records():
    database = get_db()
    rows = database.execute("SELECT payload FROM records ORDER BY created_at DESC").fetchall()
    database.close()
    import json
    return jsonify([json.loads(row["payload"]) for row in rows])


@app.route("/api/records", methods=["POST"])
@login_required
def publish_record():
    import json

    record = request.get_json(silent=True) or {}
    required_fields = {"id", "category"}
    if not required_fields.issubset(record):
        return jsonify({"error": "Record id and category are required."}), 400

    user = current_user()
    record["publishedById"] = user["id"]
    record["publishedByName"] = user["name"]
    database = get_db()
    try:
        database.execute(
            "INSERT INTO records (id, category, payload, published_by_id, published_by_name, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (record["id"], record["category"], json.dumps(record), user["id"], user["name"]),
        )
        database.commit()
    except sqlite3.IntegrityError:
        database.close()
        return jsonify({"error": "That case number has already been published."}), 409
    database.close()
    return jsonify(record), 201


@app.route("/api/records/<record_id>", methods=["DELETE"])
@login_required
def delete_record(record_id):
    database = get_db()
    result = database.execute(
        "DELETE FROM records WHERE id = ? AND published_by_id = ?",
        (record_id, current_user()["id"]),
    )
    database.commit()
    database.close()
    if result.rowcount == 0:
        return jsonify({"error": "You can only delete records you published."}), 403
    return jsonify({"deleted": record_id})


@app.route("/api/erlc/status", methods=["GET"])
@login_required
def get_erlc_status():
    """Proxy endpoint to fetch live player lists, active units, and emergency calls from ER:LC securely."""
    if not ERLC_API_KEY or ERLC_API_KEY == "your_actual_erlc_server_key_here":
        return jsonify({
            "error": "ERLC_SERVER_KEY is not configured in your .env file."
        }), 500

    try:
        headers = {
            "server-key": ERLC_API_KEY
        }
        response = requests.get(
            "https://api.erlc.gg/v2/server?Players=true&Vehicles=true&EmergencyCalls=true",
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            return jsonify({
                "error": f"ER:LC API returned status code {response.status_code}",
                "details": response.text
            }), response.status_code

        data = response.json()
        return jsonify(data)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to connect to ER:LC API: {str(e)}"}), 500


if __name__ == "__main__":
    print(f"[*] Starting Station 7 Portal Backend on http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=True)