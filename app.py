from flask import Flask, request, jsonify
from flask_cors import CORS
from sshtunnel import SSHTunnelForwarder
import psycopg
import bcrypt
import os
import uuid
from dotenv import load_dotenv

# Load .env first
load_dotenv()

# S3 config
from s3_config import s3, BUCKET_NAME, AWS_REGION

app = Flask(__name__)
CORS(app)

# SSH Tunnel Configuration
SSH_HOST = "18.190.235.250"
SSH_USER = "ec2-user"
SSH_KEY_PATH = os.path.join(os.path.dirname(__file__), "Resources", "ec2Test.pem")

# RDS Configuration
RDS_HOST = "cloudmart3-4.cjy4c6csc3wv.us-east-2.rds.amazonaws.com"
RDS_PORT = 5432
DB_NAME = "cloudmartdb"
DB_USER = "postgres"
DB_PASSWORD = "password"

# Global tunnel reference
tunnel = None


def start_ssh_tunnel():
    global tunnel
    if tunnel is None or not tunnel.is_active:
        tunnel = SSHTunnelForwarder(
            (SSH_HOST, 22),
            ssh_username=SSH_USER,
            ssh_pkey=SSH_KEY_PATH,
            remote_bind_address=(RDS_HOST, RDS_PORT),
            local_bind_address=("127.0.0.1", 0)
        )
        tunnel.start()
        print(f"SSH tunnel established on local port {tunnel.local_bind_port}")
    return tunnel


def get_db_connection():
    tun = start_ssh_tunnel()
    conn = psycopg.connect(
        host="127.0.0.1",
        port=tun.local_bind_port,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn


def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        cur.close()
        conn.close()
        print("Database initialized successfully!")

    except Exception as e:
        print(f"Error initializing database: {e}")


@app.route("/api/auth/register", methods=["POST"])
def register():
    try:
        data = request.get_json()
        email = data.get("email", "").strip()
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not email or not username or not password:
            return jsonify({"error": "Email, username, and password are required."}), 400

        if not email.lower().endswith("@my.hamptonu.edu"):
            return jsonify({"error": "Email must end with @my.hamptonu.edu."}), 400

        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(%s)", (username,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({"error": "That username is already taken."}), 409

        cur.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(%s)", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({"error": "That email already has an account."}), 409

        cur.execute(
            "INSERT INTO users (email, username, password_hash) VALUES (%s, %s, %s) RETURNING id",
            (email.lower(), username, password_hash)
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Account created successfully!", "user_id": user_id}), 201

    except Exception as e:
        print(f"Registration error: {e}")
        return jsonify({"error": "An error occurred during registration."}), 500


@app.route("/api/auth/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            return jsonify({"error": "Username and password are required."}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT id, username, password_hash FROM users WHERE LOWER(username) = LOWER(%s)",
            (username,)
        )
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user:
            return jsonify({"error": "Invalid username or password."}), 401

        user_id, db_username, password_hash = user

        if not bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8")):
            return jsonify({"error": "Invalid username or password."}), 401

        return jsonify({
            "message": "Login successful!",
            "user": {
                "id": user_id,
                "username": db_username
            }
        }), 200

    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({"error": "An error occurred during login."}), 500


# ---------------- S3 PRESIGN ROUTE ----------------
@app.route("/api/uploads/presign", methods=["POST"])
def presign_upload():
    try:
        data = request.get_json()
        file_name = data.get("fileName")
        file_type = data.get("fileType")

        print("BUCKET_NAME =", BUCKET_NAME)
        print("AWS_REGION =", AWS_REGION)

        if not file_name or not file_type:
            return jsonify({"error": "fileName and fileType are required"}), 400

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
# --------------------------------------------------


@app.route("/api/health", methods=["GET"])
def health_check():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


if __name__ == "__main__":
    print("Starting CloudMart Backend...")
    print(f"SSH Key Path: {SSH_KEY_PATH}")
    print(f"S3 Bucket: {BUCKET_NAME}")
    print(f"AWS Region: {AWS_REGION}")

    init_db()
    app.run(host="0.0.0.0", port=5001, debug=True)