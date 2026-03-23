"""
CloudMart Database Configuration
Connects to AWS RDS PostgreSQL via SSH tunnel through EC2
"""

import os
from sshtunnel import SSHTunnelForwarder
import psycopg

# SSH Tunnel Configuration
SSH_HOST = "16.59.45.159"
SSH_USER = "ec2-user"
SSH_KEY_PATH = os.path.join(os.path.dirname(__file__), "..", "Resources", "ec2Test.pem")

# RDS Configuration
RDS_HOST = "cloudmart3-4.cjy4c6csc3wv.us-east-2.rds.amazonaws.com"
RDS_PORT = 5432
DB_NAME = "cloudmartdb"
DB_USER = "postgres"
DB_PASSWORD = "password"

# Global tunnel reference
_tunnel = None


def get_tunnel():
    """Get or create SSH tunnel to EC2."""
    global _tunnel
    if _tunnel is None or not _tunnel.is_active:
        _tunnel = SSHTunnelForwarder(
            (SSH_HOST, 22),
            ssh_username=SSH_USER,
            ssh_pkey=SSH_KEY_PATH,
            remote_bind_address=(RDS_HOST, RDS_PORT),
            local_bind_address=("127.0.0.1", 0)  # 0 = auto-assign available port
        )
        _tunnel.start()
        print(f"SSH tunnel established on local port {_tunnel.local_bind_port}")
    return _tunnel


def get_connection():
    """Get database connection through SSH tunnel."""
    tunnel = get_tunnel()
    return psycopg.connect(
        host="127.0.0.1",
        port=tunnel.local_bind_port,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


def test_connection():
    """Test database connectivity."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        print(f"Connected to PostgreSQL: {version}")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False


if __name__ == "__main__":
    print("Testing database connection...")
    test_connection()
