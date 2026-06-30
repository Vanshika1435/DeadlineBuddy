from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel
from datetime import date, datetime, timedelta
import json
import os
import time
import sqlite3
import hashlib

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_name TEXT,
            deadline TEXT,
            priority TEXT,
            category TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            step_name TEXT,
            estimated_minutes INTEGER,
            status TEXT DEFAULT 'pending',
            nudge_count INTEGER DEFAULT 0,
            FOREIGN KEY (task_id) REFERENCES tasks (id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            total_points INTEGER DEFAULT 0,
            current_streak INTEGER DEFAULT 0,
            last_active_date TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def get_user_id(x_user_id: str = Header(...)) -> int:
    """Reads the logged-in user's ID from a request header.
    The frontend sends this header on every request after login."""
    try:
        return int(x_user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Missing or invalid user session")


# ---------------------------------------------------------------------------
# Gemini setup
# ---------------------------------------------------------------------------
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def call_gemini(prompt: str):
    """Calls Gemini with retry + exponential backoff. Returns the raw text or None."""
    max_retries = 4
    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            return response.text.strip().replace("```json", "").replace("```", "").strip()
        except Exception as e:
            last_error = e
            time.sleep(2 ** attempt)
    return None


# ---------------------------------------------------------------------------
# Basic routes
# ---------------------------------------------------------------------------
@app.get("/")
def home():
    return {"message": "DeadlineBuddy backend is running!"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class AuthInput(BaseModel):
    username: str
    password: str

@app.post("/signup")
def signup(input: AuthInput):
    username = input.username.strip()
    if not username or not input.password:
        return {"error": "Username and password are required"}

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return {"error": "That username is already taken"}

    cursor.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, hash_password(input.password))
    )
    user_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO user_stats (user_id, total_points, current_streak, last_active_date) VALUES (?, 0, 0, NULL)",
        (user_id,)
    )
    conn.commit()
    conn.close()

    return {"user_id": user_id, "username": username}


@app.post("/login")
def login(input: AuthInput):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM users WHERE username = ?", (input.username.strip(),))
    row = cursor.fetchone()
    conn.close()

    if row is None or row[1] != hash_password(input.password):
        return {"error": "Invalid username or password"}

    return {"user_id": row[0], "username": input.username.strip()}


# ---------------------------------------------------------------------------
# Task parsing
# ---------------------------------------------------------------------------
class TaskInput(BaseModel):
    text: str

@app.post("/parse-task")
def parse_task(input: TaskInput, user_id: int = Header(..., alias="X-User-Id")):
    prompt = f"""
You are a task-parsing assistant. From the user's message, extract:
- task_name (a short title for the task)
- deadline (the date or day mentioned; if no exact date, return the relative term like "Friday")
- priority (high/medium/low — based on deadline closeness and urgency in the message)
- category (study/work/personal/health/other)

User message: "{input.text}"

Return ONLY valid JSON, no extra text, no markdown formatting. Format:
{{"task_name": "...", "deadline": "...", "priority": "...", "category": "..."}}
"""
    raw_text = call_gemini(prompt)
    if raw_text is None:
        return {"error": "Gemini servers are busy, please try again"}

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return {"error": "Gemini did not return valid JSON", "raw": raw_text}

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (user_id, task_name, deadline, priority, category) VALUES (?, ?, ?, ?, ?)",
        (user_id, parsed["task_name"], parsed["deadline"], parsed["priority"], parsed["category"])
    )
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()

    parsed["id"] = task_id
    return parsed


@app.get("/tasks")
def get_tasks(user_id: int = Header(..., alias="X-User-Id")):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, task_name, deadline, priority, category, status FROM tasks WHERE user_id = ?",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    tasks = [
        {"id": r[0], "task_name": r[1], "deadline": r[2], "priority": r[3], "category": r[4], "status": r[5]}
        for r in rows
    ]
    return {"tasks": tasks}


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, user_id: int = Header(..., alias="X-User-Id")):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    if cursor.fetchone() is None:
        conn.close()
        return {"error": "Task not found"}

    cursor.execute("DELETE FROM steps WHERE task_id = ?", (task_id,))
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return {"message": "Task deleted", "task_id": task_id}


class PriorityUpdate(BaseModel):
    priority: str  # "high" | "medium" | "low"

@app.patch("/tasks/{task_id}/priority")
def update_priority(task_id: int, input: PriorityUpdate, user_id: int = Header(..., alias="X-User-Id")):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET priority = ? WHERE id = ? AND user_id = ?",
        (input.priority, task_id, user_id)
    )
    conn.commit()
    conn.close()
    return {"task_id": task_id, "priority": input.priority}


# ---------------------------------------------------------------------------
# Task breakdown
# ---------------------------------------------------------------------------
class BreakdownInput(BaseModel):
    task_id: int

@app.post("/breakdown-task")
def breakdown_task(input: BreakdownInput, user_id: int = Header(..., alias="X-User-Id")):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT task_name, deadline, priority, category FROM tasks WHERE id = ? AND user_id = ?",
        (input.task_id, user_id)
    )
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return {"error": "Task not found"}

    cursor.execute("SELECT COUNT(*) FROM steps WHERE task_id = ?", (input.task_id,))
    if cursor.fetchone()[0] > 0:
        conn.close()
        return {"error": "This task already has steps."}

    task_name, deadline, priority, category = row

    prompt = f"""
You are a productivity planning assistant. Break the following task into 3 to 6 small, actionable micro-steps.
Each step should take roughly 15-45 minutes and be clearly actionable (start with a verb).

Task: "{task_name}"
Deadline: {deadline}
Priority: {priority}
Category: {category}

Return ONLY valid JSON in this exact format, no extra text, no markdown:
{{"steps": [{{"step_name": "...", "estimated_minutes": 30}}, ...]}}
"""
    raw_text = call_gemini(prompt)
    if raw_text is None:
        conn.close()
        return {"error": "Gemini servers are busy, please try again"}

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        conn.close()
        return {"error": "Gemini did not return valid JSON", "raw": raw_text}

    saved_steps = []
    for step in parsed["steps"]:
        cursor.execute(
            "INSERT INTO steps (task_id, step_name, estimated_minutes) VALUES (?, ?, ?)",
            (input.task_id, step["step_name"], step["estimated_minutes"])
        )
        saved_steps.append({
            "id": cursor.lastrowid,
            "step_name": step["step_name"],
            "estimated_minutes": step["estimated_minutes"],
            "status": "pending"
        })

    conn.commit()
    conn.close()
    return {"task_id": input.task_id, "task_name": task_name, "breakdown": saved_steps}


@app.get("/tasks/{task_id}/steps")
def get_steps(task_id: int, user_id: int = Header(..., alias="X-User-Id")):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    if cursor.fetchone() is None:
        conn.close()
        return {"error": "Task not found"}

    cursor.execute(
        "SELECT id, step_name, estimated_minutes, status FROM steps WHERE task_id = ?",
        (task_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    steps = [{"id": r[0], "step_name": r[1], "estimated_minutes": r[2], "status": r[3]} for r in rows]
    return {"task_id": task_id, "steps": steps}


class StepStatusUpdate(BaseModel):
    status: str

@app.patch("/steps/{step_id}")
def update_step_status(step_id: int, input: StepStatusUpdate, user_id: int = Header(..., alias="X-User-Id")):
    clean_status = input.status.strip()

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Find which task this step belongs to, and confirm it belongs to this user
    cursor.execute("""
        SELECT steps.task_id FROM steps
        JOIN tasks ON steps.task_id = tasks.id
        WHERE steps.id = ? AND tasks.user_id = ?
    """, (step_id, user_id))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return {"error": "Step not found"}
    task_id = row[0]

    cursor.execute("UPDATE steps SET status = ? WHERE id = ?", (clean_status, step_id))

    points_earned = 0
    new_streak = None

    if clean_status == "done":
        points_earned = 10
        today_str = date.today().isoformat()

        cursor.execute("SELECT total_points, current_streak, last_active_date FROM user_stats WHERE user_id = ?", (user_id,))
        stats_row = cursor.fetchone()
        if stats_row is None:
            cursor.execute("INSERT INTO user_stats (user_id, total_points, current_streak, last_active_date) VALUES (?, 0, 0, NULL)", (user_id,))
            total_points, current_streak, last_active_date = 0, 0, None
        else:
            total_points, current_streak, last_active_date = stats_row

        if last_active_date == today_str:
            new_streak = current_streak
        elif last_active_date is None:
            new_streak = 1
        else:
            last_date = datetime.fromisoformat(last_active_date).date()
            new_streak = current_streak + 1 if (date.today() - last_date).days == 1 else 1

        new_total_points = total_points + points_earned
        cursor.execute(
            "UPDATE user_stats SET total_points = ?, current_streak = ?, last_active_date = ? WHERE user_id = ?",
            (new_total_points, new_streak, today_str, user_id)
        )

    # If every step under this task is now done, auto-mark the task as completed.
    # If any step is reopened, move the task back to pending.
    cursor.execute("SELECT status FROM steps WHERE task_id = ?", (task_id,))
    all_statuses = [r[0] for r in cursor.fetchall()]
    if all_statuses and all(s == "done" for s in all_statuses):
        cursor.execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (task_id,))
    else:
        cursor.execute("UPDATE tasks SET status = 'pending' WHERE id = ?", (task_id,))

    conn.commit()
    conn.close()

    return {
        "step_id": step_id,
        "new_status": clean_status,
        "points_earned": points_earned,
        "current_streak": new_streak
    }


# ---------------------------------------------------------------------------
# Email draft
# ---------------------------------------------------------------------------
class EmailDraftInput(BaseModel):
    task_id: int
    recipient_type: str
    reason: str

@app.post("/draft-email")
def draft_email(input: EmailDraftInput, user_id: int = Header(..., alias="X-User-Id")):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT task_name, deadline, priority FROM tasks WHERE id = ? AND user_id = ?",
        (input.task_id, user_id)
    )
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return {"error": "Task not found"}

    task_name, deadline, priority = row

    prompt = f"""
You are an assistant helping a user write a polite, professional email.

Context:
- Task: "{task_name}"
- Deadline: {deadline}
- Priority: {priority}
- Recipient type: {input.recipient_type}
- Reason for this email: {input.reason}

Write a short, polite, professional email (3-5 sentences).

Return ONLY valid JSON in this exact format, no extra text, no markdown:
{{"subject": "...", "body": "..."}}
"""
    raw_text = call_gemini(prompt)
    if raw_text is None:
        return {"error": "Gemini servers are busy, please try again"}

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return {"error": "Gemini did not return valid JSON", "raw": raw_text}

    return {"task_id": input.task_id, "task_name": task_name, "draft": parsed}


# ---------------------------------------------------------------------------
# Check-in / escalation
# ---------------------------------------------------------------------------
class CheckinInput(BaseModel):
    step_id: int

@app.post("/check-in")
def check_in(input: CheckinInput, user_id: int = Header(..., alias="X-User-Id")):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT steps.step_name, steps.status, steps.nudge_count, tasks.task_name, tasks.deadline
        FROM steps
        JOIN tasks ON steps.task_id = tasks.id
        WHERE steps.id = ? AND tasks.user_id = ?
    """, (input.step_id, user_id))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return {"error": "Step not found"}

    step_name, status, nudge_count, task_name, deadline = row

    if status == "done":
        conn.close()
        return {"message": "This step is already completed. No check-in needed."}

    new_nudge_count = nudge_count + 1
    cursor.execute("UPDATE steps SET nudge_count = ? WHERE id = ?", (new_nudge_count, input.step_id))
    conn.commit()
    conn.close()

    if new_nudge_count == 1:
        escalation_instruction = "This is the first check-in. Be gentle and friendly."
    elif new_nudge_count == 2:
        escalation_instruction = "This is the second check-in with no progress. Be a bit more direct about the deadline pressure."
    else:
        escalation_instruction = "This is the third or later check-in with no progress. Be firm and suggest concrete next actions."

    prompt = f"""
You are a supportive but honest productivity coach agent. Generate a short check-in message
(1-2 sentences) for the user about this step.

Step: "{step_name}"
Current status: {status}
Belongs to task: "{task_name}"
Task deadline: {deadline}
This is check-in number: {new_nudge_count}

Escalation guidance: {escalation_instruction}

Return ONLY valid JSON in this exact format, no extra text, no markdown:
{{"message": "...", "urgency_level": "low/medium/high"}}
"""
    raw_text = call_gemini(prompt)
    if raw_text is None:
        return {"error": "Gemini servers are busy, please try again"}

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return {"error": "Gemini did not return valid JSON", "raw": raw_text}

    return {"step_id": input.step_id, "step_name": step_name, "nudge_count": new_nudge_count, "checkin": parsed}


# ---------------------------------------------------------------------------
# Google Calendar
# ---------------------------------------------------------------------------
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_calendar_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token_file:
            token_file.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


class ScheduleEventInput(BaseModel):
    task_id: int
    step_id: int
    start_time: str
    duration_minutes: int

@app.post("/schedule-event")
def schedule_event(input: ScheduleEventInput, user_id: int = Header(..., alias="X-User-Id")):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT steps.step_name FROM steps
        JOIN tasks ON steps.task_id = tasks.id
        WHERE steps.id = ? AND tasks.user_id = ?
    """, (input.step_id, user_id))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return {"error": "Step not found"}

    step_name = row[0]

    try:
        start_dt = datetime.fromisoformat(input.start_time)
    except ValueError:
        return {"error": "start_time must look like 2026-07-01T16:00:00"}

    end_dt = start_dt + timedelta(minutes=input.duration_minutes)

    try:
        service = get_calendar_service()
        event = {
            "summary": step_name,
            "description": f"Scheduled by DeadlineBuddy for task ID {input.task_id}",
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"},
        }
        created_event = service.events().insert(calendarId="primary", body=event).execute()
    except Exception as e:
        return {"error": f"Calendar scheduling failed: {str(e)}"}

    return {"message": "Event created successfully", "event_link": created_event.get("htmlLink"), "step_name": step_name}

class CheckinInput(BaseModel):
    step_id: int

@app.post("/check-in")
def check_in(input: CheckinInput):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT steps.step_name, steps.status, steps.nudge_count, tasks.task_name, tasks.deadline
        FROM steps
        JOIN tasks ON steps.task_id = tasks.id
        WHERE steps.id = ?
    """, (input.step_id,))
    row = cursor.fetchone()

    if row is None:
        conn.close()
        return {"error": "Step not found"}

    step_name, status, nudge_count, task_name, deadline = row

    if status == "done":
        conn.close()
        return {"message": "This step is already completed. No check-in needed."}

    # Increase the nudge count each time a check-in happens for a non-completed step
    new_nudge_count = nudge_count + 1
    cursor.execute("UPDATE steps SET nudge_count = ? WHERE id = ?", (new_nudge_count, input.step_id))
    conn.commit()
    conn.close()

    # Decide escalation level based on how many times we've nudged before
    if new_nudge_count == 1:
        escalation_instruction = "This is the first check-in. Be gentle and friendly."
    elif new_nudge_count == 2:
        escalation_instruction = "This is the second check-in with no progress. Be a bit more direct about the deadline pressure."
    else:
        escalation_instruction = "This is the third or later check-in with no progress. Be firm and suggest concrete next actions, like rescheduling or seeking an extension."

    prompt = f"""
You are a supportive but honest productivity coach agent. Generate a short check-in message
(1-2 sentences) for the user about this step.

Step: "{step_name}"
Current status: {status}
Belongs to task: "{task_name}"
Task deadline: {deadline}
This is check-in number: {new_nudge_count}

Escalation guidance: {escalation_instruction}

Return ONLY valid JSON in this exact format, no extra text, no markdown:
{{"message": "...", "urgency_level": "low/medium/high"}}
"""

    max_retries = 3
    response = None
    last_error = None

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            break
        except Exception as e:
            last_error = e
            time.sleep(2 ** attempt) 

    if response is None:
        return {"error": "Gemini servers are busy, please try again", "details": str(last_error)}

    raw_text = response.text.strip()
    raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return {"error": "Gemini did not return valid JSON", "raw": raw_text}

    return {
        "step_id": input.step_id,
        "step_name": step_name,
        "nudge_count": new_nudge_count,
        "checkin": parsed
    }
# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
@app.get("/user-stats")
def get_user_stats(user_id: int = Header(..., alias="X-User-Id")):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT total_points, current_streak, last_active_date FROM user_stats WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return {"total_points": 0, "current_streak": 0, "last_active_date": None}
    return {"total_points": row[0], "current_streak": row[1], "last_active_date": row[2]}