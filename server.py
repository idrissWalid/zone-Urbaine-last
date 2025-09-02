from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import psycopg2
import os

app = Flask(__name__)
CORS(app)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-moi-en-prod")
DB_URL = os.environ.get("DATABASE_URL")  # fournie par Render (ou Supabase)

def get_conn():
    # Render/Supabase exigent souvent SSL
    return psycopg2.connect(DB_URL, sslmode="require")

# --- INITIALISATION DE LA BASE DE DONNÉES ---
def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id SERIAL PRIMARY KEY,
            candidate TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            phone TEXT NOT NULL,
            remaining_votes INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- FONCTIONS UTILES ---
def get_votes_count():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT candidate, COUNT(*) FROM votes GROUP BY candidate")
    rows = c.fetchall()
    conn.close()
    result = {row[0]: row[1] for row in rows}
    return {
        "Candidat1": result.get("Candidat1", 0),
        "Candidat2": result.get("Candidat2", 0),
        "Candidat3": result.get("Candidat3", 0),
        "Candidat4": result.get("Candidat4", 0),
        "Candidat5": result.get("Candidat5", 0)
    }

def extract_phone(text):
    start = text.find("du ")
    if start == -1:
        return None
    start += 3
    phone = text[start:start+8]
    if phone.isdigit() and len(phone) == 8:
        return phone
    return None

def add_payment(phone, votes):
    phone = extract_phone(phone)
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT remaining_votes FROM payments WHERE phone=%s", (phone,))
    row = c.fetchone()
    if row:
        new_votes = row[0] + votes
        c.execute("UPDATE payments SET remaining_votes=%s WHERE phone=%s", (new_votes, phone))
    else:
        c.execute("INSERT INTO payments (phone, remaining_votes) VALUES (%s, %s)", (phone, votes))
    conn.commit()
    conn.close()

def use_vote(phone):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT remaining_votes FROM payments WHERE phone=%s", (phone,))
    row = c.fetchone()
    if not row or row[0] <= 0:
        conn.close()
        return False
    new_votes = row[0] - 1
    c.execute("UPDATE payments SET remaining_votes=%s WHERE phone=%s", (new_votes, phone))
    conn.commit()
    conn.close()
    return True

# --- ROUTES API ---
@app.route("/api/payments", methods=["POST"])
def api_payment():
    data = request.get_json()
    phone = data.get("phone")
    votes = int(data.get("votes", 1))
    if not phone:
        return jsonify({"success": False, "error": "Numéro manquant"})
    add_payment(phone, votes)
    return jsonify({"success": True, "message": f"{votes} votes crédités pour {phone}"})

@app.route("/api/vote", methods=["POST"])
def api_vote():
    data = request.get_json()
    candidate = data.get("candidate")
    phone = data.get("phone")
    if candidate not in ["Candidat1","Candidat2","Candidat3","Candidat4","Candidat5"]:
        return jsonify({"success": False, "error": "Candidat invalide"})
    if not use_vote(phone):
        return jsonify({"success": False, "error": "Aucun vote restant pour ce numéro"})
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO votes (candidate) VALUES (%s)", (candidate,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"Vote enregistré pour {candidate}"})

@app.route("/api/admin/votes", methods=["GET"])
def admin_votes():
    votes = get_votes_count()
    return jsonify({"success": True, "votes": votes})

@app.route("/api/admin/reset_votes", methods=["POST"])
def admin_reset_votes():
    data = request.get_json()
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"success": False, "error": "Mot de passe incorrect"})
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM votes")
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Votes réinitialisés"})

# --- SERVIR LES FICHIERS STATIQUES ---
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(".", path)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
