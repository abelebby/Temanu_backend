# TemanU Backend

## Current Status

Authentication is fully set up and working. The backend is built with FastAPI and MySQL.

### What's done:
- User registration — accepts name, email, username, preferred name and password. Password is hashed before being stored.
- User login — verifies email and password, returns a JWT token
- Protected routes — any route using `Depends(get_current_user)` requires a valid JWT token in the request header

### What's not done yet:
- Health metrics endpoints (blood glucose, heart rate, oxygen saturation, blood pressure, calories, body weight)
- Activity tracking endpoints (daily steps)
- Medications endpoints (add/view medications)
- Medication logs endpoints (track whether medications were taken)

---

## Getting Started

### Prerequisites
- Python 3.8+
- MySQL

### Setup

1. Clone the repo:
```bash
git clone https://github.com/abelebby/TemanU_backend.git
cd TemanU_backend
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # Mac/Linux
.venv\Scripts\activate     # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create your `.env` file:
```bash
cp .env.example .env
```
Fill in the values — get the `DATABASE_URL` and `SECRET_KEY` from Abel privately.

Generate your own secret key:
```bash
openssl rand -hex 32
```

5. Set up the database:
```bash
mysql -u root -p < schema.sql
```

6. Run the server:
```bash
uvicorn main:app --reload
```

API runs at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

---

## Current API Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/register` | Register a new user | No |
| POST | `/login` | Login, returns JWT token | No |
| GET | `/me` | Get current user info | Yes |

---

## Notes

- Never commit your `.env` file
- Generate your own `SECRET_KEY` locally
- Database is currently local — each person runs their own MySQL instance using `schema.sql`
