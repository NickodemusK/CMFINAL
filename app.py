# Collaboration from Howard Ames, Nickodemus, and Gemini
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from sshtunnel import SSHTunnelForwarder
import psycopg
import bcrypt
import os
import uuid
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# S3 config
from s3_config import s3, BUCKET_NAME, AWS_REGION

app = Flask(__name__)
CORS(app)

# Database & Tunnel Configuration
SSH_HOST = "18.190.235.250"
SSH_USER = "ec2-user"
SSH_KEY_PATH = os.path.join(os.path.dirname(__file__), "Resources", "ec2Test.pem")

RDS_HOST = "cloudmart3-4.cjy4c6csc3wv.us-east-2.rds.amazonaws.com"
RDS_PORT = 5432
DB_NAME = "cloudmartdb"
DB_USER = "postgres"
DB_PASSWORD = "password"

tunnel = None


def start_ssh_tunnel():
    global tunnel
    if tunnel is None or not getattr(tunnel, "is_active", False):
        tunnel = SSHTunnelForwarder(
            (SSH_HOST, 22),
            ssh_username=SSH_USER,
            ssh_pkey=SSH_KEY_PATH,
            remote_bind_address=(RDS_HOST, RDS_PORT),
            local_bind_address=("127.0.0.1", 0)
        )
        tunnel.start()
    return tunnel


def get_db_connection():
    tun = start_ssh_tunnel()
    return psycopg.connect(
        host="127.0.0.1",
        port=tun.local_bind_port,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) UNIQUE,
        username VARCHAR(50) UNIQUE,
        password_hash TEXT,
        role VARCHAR(20) DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS listings (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        title VARCHAR(255),
        price NUMERIC,
        category VARCHAR(100),
        condition VARCHAR(100),
        image TEXT,
        seller VARCHAR(100),
        buyer_email VARCHAR(255),
        status VARCHAR(20) DEFAULT 'active'
    )
    """)

    # Make sure older DBs also get these columns
    cur.execute("""
    ALTER TABLE listings
    ADD COLUMN IF NOT EXISTS seller VARCHAR(100)
    """)
    cur.execute("""
    ALTER TABLE listings
    ADD COLUMN IF NOT EXISTS buyer_email VARCHAR(255)
    """)
    cur.execute("""
    ALTER TABLE listings
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active'
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS wishlist (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        listing_id INTEGER REFERENCES listings(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, listing_id)
    )
    """)

    conn.commit()
    cur.close()
    conn.close()


# ========================
# AUTH
# ========================
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    password_hash = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()
    role = data.get("role", "user")

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            "INSERT INTO users (email, username, password_hash, role) VALUES (%s, %s, %s, %s) RETURNING id",
            (data["email"], data["username"], password_hash, role)
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"user_id": user_id, "role": role}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, username, password_hash, email, role FROM users WHERE username = %s",
        (data["username"],)
    )
    user = cur.fetchone()

    cur.close()
    conn.close()

    if not user or not bcrypt.checkpw(data["password"].encode(), user[2].encode()):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "user": {
            "id": user[0],
            "username": user[1],
            "email": user[3],
            "role": user[4]
        }
    }), 200


# ========================
# LISTINGS
# ========================
@app.route("/api/listings", methods=["POST"])
def create_listing():
    data = request.get_json()
    image = data.get("image") or "https://picsum.photos/300"

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT username FROM users WHERE id = %s", (data["user_id"],))
    seller_row = cur.fetchone()
    seller_name = seller_row[0] if seller_row else "Unknown"

    cur.execute("""
        INSERT INTO listings (user_id, title, price, category, condition, image, seller, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        data["user_id"],
        data["title"],
        data["price"],
        data["category"],
        data["condition"],
        image,
        seller_name,
        "active"
    ))

    new_listing_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Listing created", "id": new_listing_id}), 201


# Homepage only shows ACTIVE listings
@app.route("/api/listings", methods=["GET"])
def get_listings():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            l.id,
            l.user_id,
            l.title,
            l.price,
            l.category,
            l.condition,
            l.image,
            COALESCE(NULLIF(l.seller, ''), u.username) AS seller,
            COALESCE(l.status, 'active') AS status,
            l.buyer_email
        FROM listings l
        LEFT JOIN users u ON l.user_id = u.id
        WHERE COALESCE(l.status, 'active') = 'active'
        ORDER BY l.id DESC
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{
        "id": r[0],
        "user_id": r[1],
        "title": r[2],
        "price": float(r[3]) if r[3] is not None else 0,
        "category": r[4],
        "condition": r[5],
        "image": r[6],
        "seller": r[7],
        "status": r[8],
        "buyer_email": r[9]
    } for r in rows]), 200


@app.route("/api/listings/<int:listing_id>", methods=["PUT"])
def update_listing(listing_id):
    data = request.get_json()
    user_id = data.get("user_id")
    user_role = data.get("role")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM listings WHERE id = %s", (listing_id,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "Listing not found"}), 404

    if user_role != "admin" and int(row[0]) != int(user_id):
        cur.close()
        conn.close()
        return jsonify({"error": "Forbidden"}), 403

    cur.execute("""
        UPDATE listings
        SET title = %s,
            price = %s,
            category = %s,
            condition = %s,
            image = %s
        WHERE id = %s
    """, (
        data["title"],
        data["price"],
        data["category"],
        data["condition"],
        data["image"],
        listing_id
    ))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True}), 200


# Mark listing as sold + store buyer email
@app.route("/api/listings/<int:listing_id>/mark-sold", methods=["PUT"])
def mark_listing_sold(listing_id):
    data = request.get_json()
    user_id = data.get("user_id")
    user_role = data.get("role")
    buyer_email = (data.get("buyer_email") or "").strip()

    if not buyer_email:
        return jsonify({"error": "Buyer email is required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM listings WHERE id = %s", (listing_id,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "Listing not found"}), 404

    if user_role != "admin" and int(row[0]) != int(user_id):
        cur.close()
        conn.close()
        return jsonify({"error": "Forbidden"}), 403

    cur.execute("""
        UPDATE listings
        SET status = 'sold',
            buyer_email = %s
        WHERE id = %s
    """, (buyer_email, listing_id))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True, "message": "Listing marked as sold"}), 200


# Optional: mark sold listing back to active
@app.route("/api/listings/<int:listing_id>/mark-active", methods=["PUT"])
def mark_listing_active(listing_id):
    data = request.get_json()
    user_id = data.get("user_id")
    user_role = data.get("role")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM listings WHERE id = %s", (listing_id,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "Listing not found"}), 404

    if user_role != "admin" and int(row[0]) != int(user_id):
        cur.close()
        conn.close()
        return jsonify({"error": "Forbidden"}), 403

    cur.execute("""
        UPDATE listings
        SET status = 'active',
            buyer_email = NULL
        WHERE id = %s
    """, (listing_id,))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True, "message": "Listing moved back to active"}), 200


@app.route("/api/listings/<int:listing_id>", methods=["DELETE"])
def delete_listing(listing_id):
    data = request.get_json()
    user_id = data.get("user_id")
    user_role = data.get("role")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM listings WHERE id = %s", (listing_id,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "Listing not found"}), 404

    if user_role != "admin" and int(row[0]) != int(user_id):
        cur.close()
        conn.close()
        return jsonify({"error": "Forbidden"}), 403

    cur.execute("DELETE FROM listings WHERE id = %s", (listing_id,))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True}), 200


# ========================
# USERS / PROFILE SUPPORT
# ========================
@app.route("/api/users/by-username/<username>", methods=["GET"])
def get_user_by_username(username):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, email, username, role, created_at
        FROM users
        WHERE LOWER(username) = LOWER(%s)
    """, (username,))
    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "id": row[0],
        "email": row[1],
        "username": row[2],
        "role": row[3],
        "created_at": str(row[4])
    }), 200


# Seller page should show BOTH active and sold
@app.route("/api/listings/by-seller/<username>", methods=["GET"])
def get_listings_by_seller(username):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            l.id,
            l.user_id,
            l.title,
            l.price,
            l.category,
            l.condition,
            l.image,
            COALESCE(NULLIF(l.seller, ''), u.username) AS seller,
            COALESCE(l.status, 'active') AS status,
            l.buyer_email
        FROM listings l
        LEFT JOIN users u ON l.user_id = u.id
        WHERE LOWER(COALESCE(NULLIF(l.seller, ''), u.username)) = LOWER(%s)
        ORDER BY l.id DESC
    """, (username,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{
        "id": r[0],
        "user_id": r[1],
        "title": r[2],
        "price": float(r[3]) if r[3] is not None else 0,
        "category": r[4],
        "condition": r[5],
        "image": r[6],
        "seller": r[7],
        "status": r[8],
        "buyer_email": r[9]
    } for r in rows]), 200


# ========================
# WISHLIST
# ========================
@app.route("/api/wishlist", methods=["GET"])
def get_wishlist():
    user_id = request.args.get("user_id")

    if not user_id:
        return jsonify([]), 200

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT l.id, l.user_id, l.title, l.price, l.category, l.condition, l.image,
               COALESCE(NULLIF(l.seller, ''), u.username) AS seller,
               COALESCE(l.status, 'active') AS status,
               l.buyer_email
        FROM wishlist w
        JOIN listings l ON w.listing_id = l.id
        LEFT JOIN users u ON l.user_id = u.id
        WHERE w.user_id = %s
        ORDER BY w.id DESC
    """, (user_id,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{
        "id": r[0],
        "user_id": r[1],
        "title": r[2],
        "price": float(r[3]) if r[3] is not None else 0,
        "category": r[4],
        "condition": r[5],
        "image": r[6],
        "seller": r[7],
        "status": r[8],
        "buyer_email": r[9]
    } for r in rows]), 200


@app.route("/api/wishlist", methods=["POST"])
def add_to_wishlist():
    data = request.get_json()
    user_id = data.get("user_id")
    listing_id = data.get("listing_id")

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO wishlist (user_id, listing_id)
            VALUES (%s, %s)
        """, (user_id, listing_id))
        conn.commit()
        return jsonify({"success": True}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()


@app.route("/api/wishlist/<int:listing_id>", methods=["DELETE"])
def remove_from_wishlist(listing_id):
    user_id = request.args.get("user_id")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM wishlist
        WHERE user_id = %s AND listing_id = %s
    """, (user_id, listing_id))
    conn.commit()

    cur.close()
    conn.close()

    return jsonify({"success": True}), 200


if __name__ == "__main__":
    init_db()
    app.run(port=5001, debug=True)