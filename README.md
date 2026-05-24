# 🏋️ AI Fitness Coach Platform — Backend

Production-grade FastAPI backend for the AI Fitness Coach Platform.
Frontend is built separately using **React + Lovable AI** and consumes these REST APIs.

---

## 🏗️ Architecture

```
app/
├── api/v1/endpoints/     # Route handlers (auth, users, workouts, diet, chat, progress, schedules, admin)
├── core/                 # Config, security (JWT), dependencies
├── database/             # SQLAlchemy async engine + session
├── models/               # ORM models (PostgreSQL schema)
├── schemas/              # Pydantic v2 request/response schemas
├── services/             # Business logic (AI service, Redis)
└── utils/                # File upload, helpers
```

---

## ⚡ Quick Start

### 1. Clone & Setup

```bash
git clone <repo>
cd ai-fitness-backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env — add your GEMINI_API_KEY, DATABASE_URL, etc.
```

### 3. Start with Docker (recommended)

```bash
docker-compose up -d
```

### 4. Or run manually

```bash
# Start PostgreSQL and Redis first, then:
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 5. Access

| URL | Purpose |
|-----|---------|
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/redoc | ReDoc |
| http://localhost:8000/health | Health check |

---

## 🔑 API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login → JWT tokens |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| POST | `/api/v1/auth/logout` | Revoke refresh token |
| POST | `/api/v1/auth/forgot-password` | Send reset email |
| POST | `/api/v1/auth/reset-password` | Reset with token |
| GET  | `/api/v1/auth/me` | Current user info |

### User Profile
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/users/onboarding` | Complete onboarding |
| GET  | `/api/v1/users/profile` | Get profile |
| PUT  | `/api/v1/users/profile` | Update profile |
| POST | `/api/v1/users/avatar` | Upload avatar |

### AI Workout Planner
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/workouts/generate` | Generate AI workout plan |
| GET  | `/api/v1/workouts/plans/active` | Get active plan |
| GET  | `/api/v1/workouts/plans` | List all plans |
| POST | `/api/v1/workouts/log` | Log workout completion |
| GET  | `/api/v1/workouts/history` | Workout history |
| GET  | `/api/v1/workouts/exercises` | Search exercises |

### AI Diet Planner
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/diet/generate` | Generate AI meal plan |
| GET  | `/api/v1/diet/plans/active` | Get active diet plan |
| GET  | `/api/v1/diet/plans/{id}/grocery-list` | Grocery list |
| GET  | `/api/v1/diet/foods/search` | Search food database |
| GET  | `/api/v1/diet/today` | Today's meals |

### AI Chat Assistant
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/chat/message` | Send message to AI coach |
| GET  | `/api/v1/chat/sessions` | List chat sessions |
| GET  | `/api/v1/chat/sessions/{id}/messages` | Session history |
| GET  | `/api/v1/chat/suggested-prompts` | Suggested prompts |

### Smart Schedule
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/schedules/generate` | Generate AI schedule |
| GET  | `/api/v1/schedules/active` | Active schedule |
| PATCH | `/api/v1/schedules/events/{id}` | Update/reschedule event |
| POST | `/api/v1/schedules/adapt` | Adaptive rescheduling |

### Progress Tracking
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/progress/log` | Log daily metrics |
| GET  | `/api/v1/progress/logs` | Progress history |
| GET  | `/api/v1/progress/summary` | Analytics summary |
| POST | `/api/v1/progress/photos` | Upload progress photo |
| GET  | `/api/v1/progress/recommendations` | AI recommendations |

### Admin (requires admin role)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET  | `/api/v1/admin/stats` | Platform analytics |
| GET  | `/api/v1/admin/users` | List users |
| PATCH | `/api/v1/admin/users/{id}/toggle-active` | Activate/deactivate |
| POST | `/api/v1/admin/exercises` | Add exercise |
| POST | `/api/v1/admin/foods` | Add food item |
| POST | `/api/v1/admin/notifications/broadcast` | Broadcast notification |

---

## 🔐 Authentication

All protected routes require:
```
Authorization: Bearer <access_token>
```

Access tokens expire in 30 minutes. Use `/auth/refresh` with the refresh token to get a new one.

---

## 🤖 AI Features

- **Workout Generation**: GPT-4 creates progressive overload plans based on goal, experience, equipment
- **Diet Planning**: Supports Indian foods, vegetarian/vegan/keto/jain diets, budget meals
- **Chat Coach**: Conversational AI with full session memory and personalization
- **Schedule Intelligence**: Adaptive rescheduling for missed workouts, extra calories, fatigue
- **Recommendations**: Progress analysis with actionable AI insights

---

## 🧪 Testing

```bash
pytest tests/ -v
```

---

## 🚀 Production Deployment

```bash
# Build and run
docker-compose -f docker-compose.yml up -d --build

# Run migrations
docker-compose exec api alembic upgrade head

# View logs
docker-compose logs -f api
```

---

## 📁 Environment Variables

See `.env.example` for all required variables. Key ones:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL async connection URL |
| `GEMINI_API_KEY` | Gemini API key (free at aistudio.google.com) |
| `JWT_SECRET_KEY` | Secret for JWT signing |
| `REDIS_URL` | Redis connection URL |

---

*Backend APIs are developed separately using FastAPI. Frontend built with React + Lovable AI.*
