# TOIR — Система технического обслуживания и ремонтов

Этот репозиторий содержит полный стек приложения TOIR, включая:
- **Frontend**: Next.js / React
- **Backend**: Python / FastAPI
- **Database**: PostgreSQL

## Запуск в режиме разработки (рекомендуемый способ)

Для запуска проекта используется Docker Compose, который поднимает все необходимые сервисы.

### Требования
- Docker
- Docker Compose

### 1. Конфигурация окружения

Создайте файл `.env` в корневой директории проекта, скопировав `.env.example`:

```bash
cp .env.example .env
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