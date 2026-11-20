from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
import os

from .database import engine, Base, get_db
from . import models
from .auth import get_password_hash
from .routers import auth, attendance, activities, fees, notifications, assessments, subject_attendance

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="High Profile Private Secondary School – Attendance",
    description="Digital attendance and class activity system",
    version="1.2.0"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

app.include_router(auth.router)
app.include_router(attendance.router)
app.include_router(activities.router)
app.include_router(fees.router)
app.include_router(notifications.router)
app.include_router(assessments.router)
app.include_router(subject_attendance.router)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/mark-attendance", response_class=HTMLResponse)
async def mark_attendance_page(request: Request):
    return templates.TemplateResponse(request, "mark_attendance.html")


@app.get("/mark-subject-attendance", response_class=HTMLResponse)
async def mark_subject_attendance_page(request: Request):
    return templates.TemplateResponse(request, "mark_subject_attendance.html")


@app.get("/report", response_class=HTMLResponse)
async def report_page(request: Request):
    return templates.TemplateResponse(request, "report.html")


@app.get("/students", response_class=HTMLResponse)
async def students_page(request: Request):
    return templates.TemplateResponse(request, "students.html")


@app.get("/activities", response_class=HTMLResponse)
async def activities_page(request: Request):
    return templates.TemplateResponse(request, "activities.html")


@app.get("/assessments", response_class=HTMLResponse)
async def assessments_page(request: Request):
    return templates.TemplateResponse(request, "assessments.html")


@app.get("/manage-students", response_class=HTMLResponse)
async def manage_students_page(request: Request):
    return templates.TemplateResponse(request, "manage_students.html")


@app.get("/manage-users", response_class=HTMLResponse)
async def manage_users_page(request: Request):
    return templates.TemplateResponse(request, "manage_users.html")


@app.get("/assign-form-teachers", response_class=HTMLResponse)
async def assign_form_teachers_page(request: Request):
    return templates.TemplateResponse(request, "assign_form_teachers.html")


@app.get("/fees", response_class=HTMLResponse)
async def fees_page(request: Request):
    return templates.TemplateResponse(request, "fees.html")


@app.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request):
    return templates.TemplateResponse(request, "notifications.html")


@app.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request):
    return templates.TemplateResponse(request, "change_password.html")
@app.get("/setup-subjects")
async def setup_subjects(db: Session = Depends(get_db)):
    """
    TEMPORARY: Replace all subjects with the school's exact subject lists.
    Visit once, then remove this route.
    """
    try:
        # Delete old subjects
        db.query(models.Subject).delete()
        db.commit()

        humanities = [
            "Mathematics",
            "History",
            "Agriculture",
            "Biology",
            "Social Studies",
            "Lifeskills",
            "English",
            "Geography",
            "Chichewa",
        ]

        sciences = [
            "Chemistry",
            "Physics",
            "Biology",
            "Agriculture",
            "Mathematics",
            "Chichewa",
            "English",
        ]

        for name in humanities:
            db.add(models.Subject(name=name, stream="Humanities", is_active=True))

        for name in sciences:
            db.add(models.Subject(name=name, stream="Sciences", is_active=True))

        db.commit()

        return JSONResponse({
            "status": "ok",
            "message": "Subjects updated successfully",
            "humanities": humanities,
            "sciences": sciences
        })
    except Exception as e:
        db.rollback()
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)
