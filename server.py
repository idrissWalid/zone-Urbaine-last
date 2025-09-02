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
    """
    Cherche un numéro de 8 chiffres dans le SMS.
    Exemple: "Vous avez recu 1000F de 78123456"
    """
    match = re.search(r"\b(\d{8})\b", text)
    if match:
        return match.group(1)
    return None

# --- GESTION DES VOTES ---
def add_or_increment_vote(phone):
    conn = get_conn()
    c = conn.cursor()
    # si numéro existe déjà → incrémente remaining_votes
    c.execute("SELECT remaining_votes FROM payments WHERE phone=%s", (phone,))
    row = c.fetchone()
    if row:
        new_votes = row[0] + 1
        c.execute("UPDATE payments SET remaining_votes=%s WHERE phone=%s", (new_votes, phone))
    else:
        c.execute("INSERT INTO payments (phone, remaining_votes) VALUES (%s, %s)", (phone, 1))
    conn.commit()
    conn.close()

# --- ROUTE PRINCIPALE POUR SMS ---
@app.route("/api/sms", methods=["POST"])
def api_sms():
    """
    Reçoit le SMS brut (Forward SMS envoie { "message": "..." }).
    On extrait le numéro et on ajoute un vote.
    """
    data = request.get_json()
    sms_text = data.get("message")
    if not sms_text:
        return jsonify({"success": False, "error": "Message vide"}), 400

    phone = extract_phone(sms_text)
    if not phone:
        return jsonify({"success": False, "error": "Aucun numéro trouvé"}), 400

    add_or_increment_vote(phone)

    return jsonify({"success": True, "message": f"1 vote ajouté pour {phone}"}), 201

# --- ADMIN ---
@app.route("/api/admin/votes", methods=["GET"])
def admin_votes():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT phone, remaining_votes FROM payments ORDER BY remaining_votes DESC;")
    rows = c.fetchall()
    conn.close()
    results = [{"phone": r[0], "votes": r[1]} for r in rows]
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
