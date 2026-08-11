# TOIR Backend (FastAPI)

This directory contains the Python FastAPI backend for the TOIR application.

## Local Development Setup

### 1. Create a Virtual Environment

It's highly recommended to use a virtual environment to manage project dependencies.

```bash
python -m venv venv
```

Activate the virtual environment:

**Windows:**
```bash
.\venv\Scripts\activate
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

### 2. Install Dependencies

Install the required Python packages from `requirements.txt`.

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file in this `backend/` directory by copying the example:

```bash
cp .env.example .env
```

Modify the `.env` file with your local database credentials and other settings. The `DATABASE_URL` should point to the PostgreSQL instance, typically running via Docker.

### 4. Run the Development Server

Start the FastAPI application using Uvicorn. The `--reload` flag will automatically restart the server when you make code changes.

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Verify

The backend server should now be running on `http://localhost:8000`.

You can test the health check endpoint by navigating to:
`http://localhost:8000/health`

You should see the following response:
```json
{
  "status": "ok",
  "service": "toir-backend"
}
```