# Cloud-Mart

A cloud-based campus marketplace for Hampton University students.

## Prerequisites

- **Python 3.10+** installed
- **The EC2 SSH key file** (`ec2Test.pem`) — required for database connection

## Setup Instructions

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd Cloud-Mart-main
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
```

### 3. Activate the virtual environment

**macOS/Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Run the application

```bash
python app.py

If it does not work do "pip install dotenv" and "pip install boto3"
```

### 6. Copy signIn.HTML path and sign in

- To run consisntently just run python app.py and run signIn.HTML

The server will start at **http://localhost:5001**

## Project Structure

```
Cloud-Mart-main/
├── app.py                 # Flask backend server
├── auth.py                # Authentication utilities
├── requirements.txt       # Python dependencies
├── docker-compose.yml     # Local PostgreSQL (optional)
├── Frontend/
│   ├── index.html         # Main page
│   ├── Signin.html        # Login/Register page
│   ├── styles.css         # Styles
│   └── script.js          # Frontend JavaScript
├── DataBase/
│   ├── postgres.py        # Database connection module
│   ├── 01_schema.sql      # Database schema
│   └── 02_seed.sql        # Seed data
└── Resources/
    ├── ec2Test.pem        # SSH key (not in Git)
    └── Images/            # Static images
```

## Configuration

| Setting | Value |
|---------|-------|
| Backend Port | `5001` |
| Database | AWS RDS PostgreSQL |
| SSH Tunnel | EC2 instance at `16.59.45.159` |

## Quick Start Checklist

- [ ] Python 3.10+ installed
- [ ] Project files cloned/copied
- [ ] `Resources/ec2Test.pem` file present
- [ ] Virtual environment created and activated
- [ ] Dependencies installed
- [ ] Run with `python app.py`

## Troubleshooting

**Port 5001 already in use:**
```bash
# Find and kill the process using port 5001
lsof -i :5001
kill -9 <PID>
```

**SSH key permission error:**
```bash
chmod 600 Resources/ec2Test.pem
```

**Database connection failed:**
- Ensure you have internet access
- Verify the `ec2Test.pem` file is in the correct location
- Check that the EC2 instance is running
