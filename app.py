#Collaboration from Howard Ames, 
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from sshtunnel import SSHTunnelForwarder
import psycopg
import bcrypt
import os
import uuid
from dotenv import load_dotenv

# Load environment variables from .env - Nickodemus
load_dotenv()

# S3 config - Nickodemus
from s3_config import s3, BUCKET_NAME, AWS_REGION

app = Flask(__name__)
CORS(app)

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
        password_hash TEXT
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
        image TEXT
    )
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

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO users (email, username, password_hash) VALUES (%s, %s, %s) RETURNING id",
        (data["email"], data["username"], password_hash)
    )

    user_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"user_id": user_id}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, username, password_hash FROM users WHERE username = %s",
        (data["username"],)
    )
    user = cur.fetchone()

    cur.close()
    conn.close()

    if not user or not bcrypt.checkpw(data["password"].encode(), user[2].encode()):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({"user": {"id": user[0], "username": user[1]}}), 200


# ========================
# S3 Nickodemus 
# ========================
@app.route("/api/uploads/presign", methods=["POST"])
def presign_upload():
    try:
        data = request.get_json()
        file_name = data.get("fileName")
        file_type = data.get("fileType")

        if not file_name:
            return jsonify({"error": "fileName is required"}), 400

        if not BUCKET_NAME or not AWS_REGION:
            return jsonify({"error": "S3 environment variables are not configured correctly"}), 500

        ext = file_name.split(".")[-1].lower()
        key = f"listings/{uuid.uuid4()}.{ext}"

        upload_url = s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": key,
                "ContentType": file_type
            },
            ExpiresIn=300,
            HttpMethod="PUT"
        )

        image_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"

        return jsonify({
            "uploadUrl": upload_url,
            "key": key,
            "imageUrl": image_url
        }), 200

    except Exception as e:
        print(f"Presign error: {e}")
        return jsonify({"error": "Failed to generate presigned URL"}), 500


# ========================
# LISTINGS
# ========================
@app.route("/api/listings", methods=["POST"])
def create_listing():
    data = request.get_json()
    image = data.get("image") or "https://picsum.photos/300"

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO listings (user_id, title, price, category, condition, image)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        data["user_id"],
        data["title"],
        data["price"],
        data["category"],
        data["condition"],
        image
    ))

    new_listing_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Listing created", "id": new_listing_id}), 201


@app.route("/api/listings", methods=["GET"])
def get_listings():
    category = request.args.get("category")
    search = request.args.get("search")

    conn = get_db_connection()
    cur = conn.cursor()

    query = """
        SELECT l.id, l.user_id, l.title, l.price, l.category, l.condition, l.image, u.username
        FROM listings l
        LEFT JOIN users u ON l.user_id = u.id
        WHERE 1=1
    """
    params = []

    if category:
        query += " AND l.category = %s"
        params.append(category)

    if search:
        query += " AND LOWER(l.title) LIKE %s"
        params.append(f"%{search.lower()}%")

    query += " ORDER BY l.id DESC"

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {
            "id": r[0],
            "user_id": r[1],
            "title": r[2],
            "price": float(r[3]) if r[3] is not None else None,
            "category": r[4],
            "condition": r[5],
            "image": r[6],
            "seller": r[7]
        }
        for r in rows
    ]), 200


@app.route("/api/listings/<int:listing_id>", methods=["GET"])
def get_single_listing(listing_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT l.id, l.user_id, l.title, l.price, l.category, l.condition, l.image, u.username
        FROM listings l
        LEFT JOIN users u ON l.user_id = u.id
        WHERE l.id = %s
    """, (listing_id,))

    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({"error": "Listing not found"}), 404

    return jsonify({
        "id": row[0],
        "user_id": row[1],
        "title": row[2],
        "price": float(row[3]) if row[3] is not None else None,
        "category": row[4],
        "condition": row[5],
        "image": row[6],
        "seller": row[7]
    }), 200


@app.route("/api/listings/<int:listing_id>", methods=["PUT"])
def update_listing(listing_id):
    data = request.get_json()
    user_id = data.get("user_id")
    title = data.get("title")
    price = data.get("price")
    category = data.get("category")
    condition = data.get("condition")
    image = data.get("image")

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid user_id"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM listings WHERE id = %s", (listing_id,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "Listing not found"}), 404

    if int(row[0]) != user_id:
        cur.close()
        conn.close()
        return jsonify({"error": "Forbidden"}), 403

    cur.execute("""
        UPDATE listings
        SET title = %s, price = %s, category = %s, condition = %s, image = %s
        WHERE id = %s
        RETURNING id, user_id, title, price, category, condition, image
    """, (title, price, category, condition, image, listing_id))

    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "listing": {
            "id": updated[0],
            "user_id": updated[1],
            "title": updated[2],
            "price": float(updated[3]) if updated[3] is not None else None,
            "category": updated[4],
            "condition": updated[5],
            "image": updated[6]
        }
    }), 200


@app.route("/api/listings/<int:listing_id>", methods=["DELETE"])
def delete_listing(listing_id):
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id") or request.args.get("user_id")

    if user_id is None:
        return jsonify({"error": "user_id is required"}), 400

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid user_id"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM listings WHERE id = %s", (listing_id,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "Listing not found"}), 404

    if int(row[0]) != user_id:
        cur.close()
        conn.close()
        return jsonify({"error": "Forbidden"}), 403

    cur.execute("DELETE FROM listings WHERE id = %s", (listing_id,))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True}), 200


# ========================
# WISHLIST
# ========================
@app.route("/api/wishlist", methods=["GET"])
def get_wishlist():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT l.id, l.user_id, l.title, l.price, l.category, l.condition, l.image, u.username
        FROM wishlist w
        JOIN listings l ON w.listing_id = l.id
        LEFT JOIN users u ON l.user_id = u.id
        WHERE w.user_id = %s
        ORDER BY w.created_at DESC
    """, (user_id,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {
            "id": r[0],
            "user_id": r[1],
            "title": r[2],
            "price": float(r[3]) if r[3] is not None else None,
            "category": r[4],
            "condition": r[5],
            "image": r[6],
            "seller": r[7]
        }
        for r in rows
    ]), 200


@app.route("/api/wishlist", methods=["POST"])
def add_to_wishlist():
    data = request.get_json()
    user_id = data.get("user_id")
    listing_id = data.get("listing_id")

    if not user_id or not listing_id:
        return jsonify({"error": "user_id and listing_id are required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            "INSERT INTO wishlist (user_id, listing_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, listing_id)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"error": str(e)}), 500

    cur.close()
    conn.close()

    return jsonify({"message": "Added to wishlist"}), 201


@app.route("/api/wishlist/<int:listing_id>", methods=["DELETE"])
def remove_from_wishlist(listing_id):
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM wishlist WHERE user_id = %s AND listing_id = %s",
        (user_id, listing_id)
    )

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Removed from wishlist"}), 200


# ========================
# SERVE FRONTEND FILES
# ========================
@app.route("/")
def serve_signin():
    return send_from_directory("Frontend", "Signin.html")


@app.route("/home")
def serve_index():
    return send_from_directory("Frontend", "index.html")


@app.route("/create")
def serve_create():
    return send_from_directory("Frontend", "create.html")


@app.route("/wishlist")
def serve_wishlist():
    return send_from_directory("Frontend", "wishlist.html")


@app.route("/Frontend/<path:filename>")
def serve_frontend_files(filename):
    return send_from_directory("Frontend", filename)


@app.route("/Resources/<path:filename>")
def serve_resources(filename):
    return send_from_directory("Resources", filename)


if __name__ == "__main__":
    init_db()
    app.run(port=5001, debug=True)
