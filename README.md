# DeadlineBuddy

An AI-powered productivity assistant that transforms deadlines into manageable action plans. Instead of simply reminding users about pending tasks, DeadlineBuddy helps them organize work, break tasks into smaller steps, track progress, and stay accountable.

## Overview

DeadlineBuddy is designed to address a common productivity problem: knowing what needs to be completed but struggling to decide how and when to start.

Users can describe tasks in natural language, and the application uses AI to identify task details, estimate priority, and create actionable steps. It also provides progress tracking, contextual check-ins, and communication assistance to help users stay on track.

## Features

- **Natural Language Task Creation:** Describe a task in everyday language. The AI extracts the task name, deadline, priority, and category.
- **AI Task Breakdown:** Convert larger tasks into smaller, actionable steps that are easier to complete.
- **Priority Management:** Organize tasks according to their urgency and importance.
- **Progress Tracking:** Update individual step statuses and track overall task completion.
- **AI-Powered Check-ins:** Generate contextual follow-up messages based on task progress and previous check-ins.
- **Escalation Logic:** Adjust the tone of check-ins as repeated delays occur.
- **Email Draft Generation:** Generate professional email drafts using task details, deadlines, recipient type, and the reason for writing.
- **Productivity Tracking:** Earn points and maintain activity streaks through task completion.
- **Task Management:** View, update, prioritize, and delete tasks.
- **Calendar Integration:** Includes Google Calendar event scheduling functionality through Google OAuth.

## Technology Stack

| Component | Technologies |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, FastAPI |
| AI Integration | Google Gemini API |
| AI Model | Gemini 2.5 Flash |
| Database | SQLite |
| API Validation | Pydantic |
| Calendar Integration | Google Calendar API |
| Authentication | Application-level user registration and login |
| Deployment | Vercel, Render |

## System Architecture

DeadlineBuddy follows a frontend-backend architecture. The frontend communicates with a FastAPI backend, which handles task operations, AI requests, and database interactions.

```text
                  User
                   |
                   v
            Frontend Application
             HTML / CSS / JS
                   |
                   v
              FastAPI Backend
                   |
       +-----------+------------+
       |           |            |
       v           v            v
   Task Logic   AI Service   User & Task
       |           |         Management
       |           v            |
       |      Gemini API        |
       |           |            |
       +-----------+------------+
                   |
                   v
                SQLite
                   |
                   v
          Persistent Task Data

                   |
                   v
           External Integrations
                   |
             Google Calendar
```

## How It Works

### 1. Natural Language Task Creation

The user enters a task in a conversational format.

For example:

```text
I need to prepare my project presentation by Friday.
It is very important.
```

The backend sends the input to Gemini, which extracts structured information:

- Task name
- Deadline
- Priority
- Category

The resulting task is saved in the database.

### 2. AI-Powered Task Breakdown

When a user selects the breakdown option, the backend retrieves the task details and sends them to Gemini.

The AI generates approximately 3–6 actionable micro-steps, designed to make the task easier to approach.

Each step can be tracked independently.

### 3. Progress Tracking

Users can update the status of individual steps.

The application uses these updates to maintain task progress and determine whether the overall task is pending or completed.

Points and activity streaks are also updated based on completed work.

### 4. Intelligent Check-ins

DeadlineBuddy provides contextual check-ins for incomplete steps.

The backend tracks the number of previous check-ins and uses that information to adjust the generated message:

- First check-in: Friendly and supportive.
- Second check-in: More direct about deadline pressure.
- Subsequent check-ins: Firmer guidance with suggested next actions.

This creates a more context-aware accountability experience than a basic reminder.

### 5. Email Draft Generation

Users can request an email draft related to a task.

The backend provides Gemini with relevant task information, recipient type, and the reason for writing. The AI generates a professional subject and email body.

### 6. Calendar Scheduling

The backend includes Google Calendar API integration to schedule task steps as calendar events.

This functionality requires Google OAuth credentials and authorization to access the user's calendar.

## Project Structure

```text
DeadlineBuddy/
│
├── frontend/
│   └── index.html
│
├── main.py
├── requirements.txt
├── vercel.json
├── .gitignore
└── README.md
```

## Local Setup

### Prerequisites

- Python 3.10+
- Git
- Google Gemini API key

Google Calendar functionality additionally requires Google Cloud OAuth credentials.

### 1. Clone the repository

```bash
git clone https://github.com/Vanshika1435/DeadlineBuddy.git
cd DeadlineBuddy
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Windows:

```powershell
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key
```

Keep your API key private and never commit the `.env` file.

### 5. Start the backend

```bash
uvicorn main:app --reload
```

The backend will run at:

```text
http://127.0.0.1:8000
```

Interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

### 6. Run the frontend

Open `frontend/index.html` through a local development server, such as VS Code Live Server.

Make sure the frontend API base URL points to the locally running backend.

## Deployment

| Component | Platform |
|---|---|
| Frontend | Vercel |
| Backend | Render |
| AI Integration | Google Gemini API |
| Database | SQLite |

**Live Application:** https://deadline-buddy-nu.vercel.app/

**Backend API:** https://deadlinebuddy-aliw.onrender.com

The application uses a separate frontend and backend deployment. The backend requires its Gemini API key to be configured in the deployment environment.

Google Calendar scheduling additionally requires OAuth configuration and authorization.

## Key Learning Outcomes

- Integrating generative AI into a practical productivity application.
- Converting unstructured natural language into structured task data.
- Designing AI-powered task decomposition and progress workflows.
- Building REST APIs using FastAPI.
- Managing relational task and step data using SQLite.
- Implementing contextual prompts and escalation logic.
- Integrating external services such as Google Calendar.
- Deploying a full-stack application using Vercel and Render.

## Future Improvements

- Automated deadline monitoring and scheduled notifications.
- More advanced workload prioritization.
- Improved progress analytics and productivity insights.
- Expanded calendar synchronization and scheduling workflows.

---

**Author:** Vanshika Sharma

**Repository:** https://github.com/Vanshika1435/DeadlineBuddy
