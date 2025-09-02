from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import psycopg2
import os
import re

app = Flask(__name__)
CORS(app)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-moi-en-prod")
DB_URL = os.environ.get("DATABASE_URL")  # fournie par Render

def get_conn():
    return psycopg2.connect(DB_URL, sslmode="require")

# --- INITIALISATION DE LA BASE ---
def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id SERIAL PRIMARY KEY,
            candidate TEXT NOT NULL,
            phone TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            phone TEXT NOT NULL UNIQUE,
            remaining_votes INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- EXTRACTION DU NUMERO ---
def extract_phone(text):
    match = re.search(r"\b(\d{8})\b", text)
    if match:
        return match.group(1)
    return None

# --- GESTION DES VOTES ---
def add_vote(phone, candidate, votes=1):
    conn = get_conn()
    c = conn.cursor()
    # Vérifie si le téléphone a des votes disponibles
    c.execute("SELECT remaining_votes FROM payments WHERE phone=%s", (phone,))
    row = c.fetchone()
    if row and row[0] >= votes:
        # Ajoute le vote(s)
        for _ in range(votes):
            c.execute("INSERT INTO votes (candidate, phone) VALUES (%s, %s)", (candidate, phone))
        # Décrémente les votes disponibles
        c.execute("UPDATE payments SET remaining_votes = remaining_votes - %s WHERE phone=%s", (votes, phone))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

# --- ROUTES PUBLIQUES ---

@app.route("/api/vote", methods=["POST"])
def api_vote():
    data = request.get_json()
    phone = data.get("phone")
    candidate = data.get("candidate")
    votes = int(data.get("votes", 1))

    if not phone or len(phone) != 8:
        return jsonify({"success": False, "error": "Numéro invalide"}), 400
    if not candidate:
        return jsonify({"success": False, "error": "Candidat non spécifié"}), 400

    if add_vote(phone, candidate, votes):
        return jsonify({"success": True, "message": f"{votes} vote(s) ajouté(s) pour {candidate}"}), 201
    else:
        return jsonify({"success": False, "error": "Pas assez de votes disponibles pour ce numéro"}), 400

# --- ROUTES ADMIN ---

@app.route("/api/admin/votes_by_candidate", methods=["GET"])
def admin_votes_by_candidate():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT candidate, COUNT(*) FROM votes GROUP BY candidate")
    rows = c.fetchall()
    conn.close()
    results = {row[0]: row[1] for row in rows}
    return jsonify({"success": True, "votes": results})

@app.route("/api/admin/reset_votes", methods=["POST"])
def admin_reset_votes():
    data = request.get_json()
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"success": False, "error": "Mot de passe incorrect"})
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM payments")
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

# --- MAIN ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
