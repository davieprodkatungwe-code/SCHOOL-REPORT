from typing import List, Optional
from datetime import date, datetime
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

from .. import models, schemas, auth, database

router = APIRouter(prefix="/api", tags=["Attendance"])


# =========================
# CLASSES
# =========================

@router.get("/classes")
async def get_classes(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    try:
        classes = (
            db.query(models.Class)
            .order_by(models.Class.form.asc(), models.Class.stream.asc(), models.Class.name.asc())
            .all()
        )
        result = []
        for c in classes:
            result.append({
                "id": c.id,
                "name": c.name or "",
                "form": c.form,
                "stream": c.stream or ""
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load classes: {str(e)}")

@router.get("/classes-with-teachers")
async def get_classes_with_teachers(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    classes = db.query(models.Class).order_by(models.Class.form, models.Class.stream).all()
    result = []
    for c in classes:
        result.append({
            "id": c.id,
            "name": c.name,
            "form": c.form,
            "stream": c.stream,
            "form_teacher_id": c.form_teacher_id,
            "form_teacher_name": c.form_teacher.full_name if c.form_teacher else None
        })
    return result


@router.put("/classes/{class_id}/form-teacher")
async def assign_form_teacher(
    class_id: int,
    teacher_id: int = Query(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can assign form teachers")

    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    teacher = db.query(models.User).filter(models.User.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    class_obj.form_teacher_id = teacher_id
    if teacher.role == "teacher":
        teacher.role = "form_teacher"
    db.commit()

    return {
        "message": f"{teacher.full_name} is now Form Teacher for {class_obj.name}",
        "class": class_obj.name,
        "form_teacher": teacher.full_name
    }


# =========================
# STUDENTS
# =========================

@router.get("/classes/{class_id}/students")
async def get_students_for_class(
    class_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    students = (
        db.query(models.Student)
        .filter(
            models.Student.class_id == class_id,
            models.Student.is_active == True
        )
        .order_by(
            models.Student.last_name.asc(),
            models.Student.first_name.asc(),
            models.Student.admission_number.asc()
        )
        .all()
    )

    # Also sort in Python by full name (extra safety)
    students = sorted(
        students,
        key=lambda s: ((s.last_name or "").lower(), (s.first_name or "").lower(), s.admission_number or "")
    )

    result = []
    for s in students:
        result.append({
            "id": s.id,
            "admission_number": s.admission_number,
            "first_name": s.first_name,
            "last_name": s.last_name,
            "full_name": s.full_name,
            "gender": s.gender,
            "parent_phone": s.parent_phone,
            "parent_name": s.parent_name,
            "class_id": s.class_id
        })
    return result

@router.post("/students")
async def create_student(
    payload: schemas.StudentCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    existing = db.query(models.Student).filter(
        models.Student.admission_number == payload.admission_number
    ).first()

    if existing and existing.is_active:
        raise HTTPException(status_code=400, detail="Admission number already exists")

    if existing and not existing.is_active:
        existing.is_active = True
        existing.first_name = payload.first_name
        existing.last_name = payload.last_name
        existing.class_id = payload.class_id
        existing.gender = payload.gender
        existing.parent_phone = payload.parent_phone
        existing.parent_name = payload.parent_name
        db.commit()
        db.refresh(existing)
        return {
            "message": "Student restored and updated successfully",
            "id": existing.id,
            "full_name": existing.full_name
        }

    class_obj = db.query(models.Class).filter(models.Class.id == payload.class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    student = models.Student(
        admission_number=payload.admission_number,
        first_name=payload.first_name,
        last_name=payload.last_name,
        class_id=payload.class_id,
        gender=payload.gender,
        parent_phone=payload.parent_phone,
        parent_name=payload.parent_name,
        is_active=True
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    return {
        "message": "Student added successfully",
        "id": student.id,
        "full_name": student.full_name
    }


@router.put("/students/{student_id}")
async def update_student(
    student_id: int,
    payload: schemas.StudentCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    existing = db.query(models.Student).filter(
        models.Student.admission_number == payload.admission_number,
        models.Student.id != student_id
    ).first()
    if existing and existing.is_active:
        raise HTTPException(status_code=400, detail="Admission number already used by another student")

    class_obj = db.query(models.Class).filter(models.Class.id == payload.class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    student.admission_number = payload.admission_number
    student.first_name = payload.first_name
    student.last_name = payload.last_name
    student.class_id = payload.class_id
    student.gender = payload.gender
    student.parent_phone = payload.parent_phone
    student.parent_name = payload.parent_name
    student.is_active = True

    db.commit()
    db.refresh(student)

    return {
        "message": "Student updated successfully",
        "id": student.id,
        "full_name": student.full_name
    }


@router.delete("/students/{student_id}")
async def delete_student(
    student_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    name = student.full_name
    student.is_active = False
    db.commit()

    return {"message": f"Student {name} removed successfully"}


@router.post("/students/import-excel")
async def import_students_excel(
    class_id: int = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx)")

    content = await file.read()
    try:
        wb = load_workbook(filename=BytesIO(content), data_only=True)
        ws = wb.active
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read Excel file")

    headers = {}
    for col in range(1, ws.max_column + 1):
        value = ws.cell(1, col).value
        if value is not None:
            headers[str(value).strip().lower()] = col

    required = ["admission_number", "first_name", "last_name"]
    for r in required:
        if r not in headers:
            raise HTTPException(
                status_code=400,
                detail=f"Missing column '{r}'. Required: admission_number, first_name, last_name"
            )

    added = 0
    skipped = 0
    restored = 0
    errors = []

    for row in range(2, ws.max_row + 1):
        admission_number = str(ws.cell(row, headers["admission_number"]).value or "").strip()
        first_name = str(ws.cell(row, headers["first_name"]).value or "").strip()
        last_name = str(ws.cell(row, headers["last_name"]).value or "").strip()

        if not admission_number and not first_name and not last_name:
            continue

        if not admission_number or not first_name or not last_name:
            errors.append(f"Row {row}: missing required fields")
            skipped += 1
            continue

        gender = None
        parent_phone = None
        parent_name = None
        if "gender" in headers:
            gender = str(ws.cell(row, headers["gender"]).value or "").strip() or None
        if "parent_phone" in headers:
            parent_phone = str(ws.cell(row, headers["parent_phone"]).value or "").strip() or None
        if "parent_name" in headers:
            parent_name = str(ws.cell(row, headers["parent_name"]).value or "").strip() or None

        existing = db.query(models.Student).filter(
            models.Student.admission_number == admission_number
        ).first()

        if existing and existing.is_active:
            skipped += 1
            continue

        if existing and not existing.is_active:
            existing.is_active = True
            existing.first_name = first_name
            existing.last_name = last_name
            existing.class_id = class_id
            existing.gender = gender
            existing.parent_phone = parent_phone
            existing.parent_name = parent_name
            restored += 1
            continue

        student = models.Student(
            admission_number=admission_number,
            first_name=first_name,
            last_name=last_name,
            class_id=class_id,
            gender=gender,
            parent_phone=parent_phone,
            parent_name=parent_name,
            is_active=True
        )
        db.add(student)
        added += 1

    db.commit()

    return {
        "message": f"Import finished for {class_obj.name}",
        "added": added,
        "restored": restored,
        "skipped": skipped,
        "errors": errors[:10]
    }


@router.post("/students/{student_id}/transfer")
async def transfer_student(
    student_id: int,
    new_class_id: int = Query(...),
    year: int = Query(...),
    academic_year: Optional[str] = Query(None),
    notes: Optional[str] = Query(None),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    new_class = db.query(models.Class).filter(models.Class.id == new_class_id).first()
    if not new_class:
        raise HTTPException(status_code=404, detail="New class not found")

    if student.class_id == new_class_id:
        raise HTTPException(status_code=400, detail="Student is already in that class")

    history = models.StudentClassHistory(
        student_id=student.id,
        class_id=student.class_id,
        year=year,
        academic_year=academic_year or str(year),
        notes=notes or "Transferred from previous class"
    )
    db.add(history)

    old_class_name = student.class_.name if student.class_ else "Unknown"
    student.class_id = new_class_id
    db.commit()

    return {
        "message": f"{student.full_name} moved from {old_class_name} to {new_class.name}. History saved for year {year}.",
        "student_id": student.id,
        "new_class": new_class.name
    }


@router.get("/students/{student_id}/history")
async def get_student_history(
    student_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    history = (
        db.query(models.StudentClassHistory)
        .filter(models.StudentClassHistory.student_id == student_id)
        .order_by(models.StudentClassHistory.year.desc())
        .all()
    )

    result = []
    for h in history:
        result.append({
            "id": h.id,
            "class_name": h.class_.name if h.class_ else "Unknown",
            "year": h.year,
            "academic_year": h.academic_year,
            "notes": h.notes,
            "recorded_at": h.created_at
        })

    return {
        "student_id": student.id,
        "full_name": student.full_name,
        "admission_number": student.admission_number,
        "current_class": student.class_.name if student.class_ else None,
        "history": result
    }


# =========================
# DAILY ATTENDANCE
# =========================

@router.post("/attendance/mark")
async def mark_attendance(
    payload: schemas.AttendanceBulk,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    class_obj = db.query(models.Class).filter(models.Class.id == payload.class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    saved = 0
    for record in payload.records:
        student = db.query(models.Student).filter(
            models.Student.id == record.student_id,
            models.Student.class_id == payload.class_id
        ).first()
        if not student:
            continue

        existing = db.query(models.Attendance).filter(
            and_(
                models.Attendance.student_id == record.student_id,
                models.Attendance.date == payload.date
            )
        ).first()

        if existing:
            existing.status = record.status.value
            existing.reason = record.reason if record.status == schemas.AttendanceStatus.absent else None
            existing.communicated = record.communicated.value if record.status == schemas.AttendanceStatus.absent else "unknown"
            existing.notes = record.notes
            existing.recorded_by = current_user.id
            existing.updated_at = datetime.utcnow()
            attendance_record = existing
        else:
            new_record = models.Attendance(
                student_id=record.student_id,
                class_id=payload.class_id,
                date=payload.date,
                status=record.status.value,
                reason=record.reason if record.status == schemas.AttendanceStatus.absent else None,
                communicated=record.communicated.value if record.status == schemas.AttendanceStatus.absent else "unknown",
                notes=record.notes,
                recorded_by=current_user.id
            )
            db.add(new_record)
            db.flush()
            attendance_record = new_record

        if record.status == schemas.AttendanceStatus.absent:
            existing_notif = db.query(models.Notification).filter(
                models.Notification.student_id == student.id,
                models.Notification.date == payload.date
            ).first()
            if not existing_notif:
                message = f"Dear Parent, your child {student.full_name} was marked absent on {payload.date}."
                if record.reason:
                    message += f" Reason: {record.reason}."
                notif = models.Notification(
                    student_id=student.id,
                    attendance_id=attendance_record.id,
                    date=payload.date,
                    parent_phone=student.parent_phone,
                    parent_name=student.parent_name,
                    message=message,
                    status="pending"
                )
                db.add(notif)

        saved += 1

    db.commit()
    return {"message": f"Attendance saved successfully for {saved} students", "saved": saved}


@router.get("/attendance/{class_id}")
async def get_attendance(
    class_id: int,
    attendance_date: date = Query(..., alias="date"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    records = (
        db.query(models.Attendance)
        .filter(
            models.Attendance.class_id == class_id,
            models.Attendance.date == attendance_date
        )
        .all()
    )
    result = []
    for r in records:
        result.append({
            "id": r.id,
            "student_id": r.student_id,
            "status": r.status,
            "reason": r.reason,
            "communicated": r.communicated,
            "notes": r.notes
        })
    return result


@router.get("/report/{class_id}")
async def get_report(
    class_id: int,
    report_date: date = Query(..., alias="date"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    students = (
        db.query(models.Student)
        .filter(models.Student.class_id == class_id, models.Student.is_active == True)
        .order_by(models.Student.last_name, models.Student.first_name)
        .all()
    )
    total_students = len(students)

    records = (
        db.query(models.Attendance)
        .filter(
            models.Attendance.class_id == class_id,
            models.Attendance.date == report_date
        )
        .all()
    )
    record_map = {r.student_id: r for r in records}

    present_count = 0
    absent_count = 0
    absentees = []

    for student in students:
        rec = record_map.get(student.id)
        if rec:
            if rec.status == "present":
                present_count += 1
            else:
                absent_count += 1
                absentees.append({
                    "student_name": student.full_name,
                    "admission_number": student.admission_number,
                    "reason": rec.reason or "Not specified",
                    "communicated": rec.communicated
                })

    percentage = round((present_count / total_students * 100), 1) if total_students else 0

    return {
        "class_name": class_obj.name,
        "date": str(report_date),
        "total_students": total_students,
        "total_present": present_count,
        "total_absent": absent_count,
        "present_percentage": percentage,
        "absentees": absentees
    }


@router.get("/report/{class_id}/excel")
async def download_excel_report(
    class_id: int,
    report_date: date = Query(..., alias="date"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    class_obj = db.query(models.Class).filter(models.Class.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    students = (
        db.query(models.Student)
        .filter(models.Student.class_id == class_id, models.Student.is_active == True)
        .order_by(models.Student.last_name, models.Student.first_name)
        .all()
    )
    total_students = len(students)

    records = (
        db.query(models.Attendance)
        .filter(
            models.Attendance.class_id == class_id,
            models.Attendance.date == report_date
        )
        .all()
    )
    record_map = {r.student_id: r for r in records}

    present_count = 0
    absent_count = 0
    student_rows = []
    absentees = []

    for student in students:
        rec = record_map.get(student.id)
        if rec:
            status = rec.status.capitalize()
            reason = rec.reason or ""
            communicated = rec.communicated
            if rec.status == "present":
                present_count += 1
            else:
                absent_count += 1
                absentees.append({
                    "name": student.full_name,
                    "admission": student.admission_number,
                    "reason": reason or "Not specified",
                    "communicated": communicated
                })
        else:
            status = "Not marked"
            reason = ""
            communicated = ""

        student_rows.append({
            "admission": student.admission_number,
            "name": student.full_name,
            "status": status,
            "reason": reason,
            "communicated": communicated
        })

    activities = (
        db.query(models.ClassActivity)
        .filter(
            models.ClassActivity.class_id == class_id,
            models.ClassActivity.date == report_date
        )
        .order_by(models.ClassActivity.created_at)
        .all()
    )

    subject_records = (
        db.query(models.SubjectAttendance)
        .filter(
            models.SubjectAttendance.class_id == class_id,
            models.SubjectAttendance.date == report_date
        )
        .all()
    )
    subject_map = {}
    for r in subject_records:
        if r.student_id not in subject_map:
            subject_map[r.student_id] = []
        subject_map[r.student_id].append({
            "subject_name": r.subject.name if r.subject else "Unknown",
            "status": r.status,
            "reason": r.reason or ""
        })

    form_teacher_name = class_obj.form_teacher.full_name if class_obj.form_teacher else "Not assigned"

    wb = Workbook()
    ws = wb.active
    ws.title = "Daily Report"

    title_font = Font(name="Calibri", size=16, bold=True, color="0A2540")
    subtitle_font = Font(name="Calibri", size=12, bold=True)
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    section_font = Font(name="Calibri", size=12, bold=True, color="0A2540")
    normal_font = Font(name="Calibri", size=11)
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin")
    )
    header_fill = PatternFill(start_color="0A2540", end_color="0A2540", fill_type="solid")
    present_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    absent_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

    ws.merge_cells("A1:F1")
    ws["A1"] = "HIGH PROFILE PRIVATE SECONDARY SCHOOL"
    ws["A1"].font = title_font
    ws["A1"].alignment = Alignment(horizontal="center")

    ws.merge_cells("A2:F2")
    ws["A2"] = "DAILY ATTENDANCE REPORT"
    ws["A2"].font = subtitle_font
    ws["A2"].alignment = Alignment(horizontal="center")

    ws.merge_cells("A3:F3")
    ws["A3"] = f"Class: {class_obj.name}  |  Date: {report_date.strftime('%d %B %Y')}  |  Form Teacher: {form_teacher_name}"
    ws["A3"].font = Font(name="Calibri", size=11)
    ws["A3"].alignment = Alignment(horizontal="center")

    ws["A5"] = "ATTENDANCE SUMMARY"
    ws["A5"].font = section_font
    ws["A6"] = "Total Students"
    ws["B6"] = total_students
    ws["A7"] = "Present"
    ws["B7"] = present_count
    ws["A8"] = "Absent"
    ws["B8"] = absent_count
    ws["A9"] = "Present %"
    ws["B9"] = f"{round((present_count / total_students * 100), 1) if total_students else 0}%"

    row = 11
    ws[f"A{row}"] = "FULL STUDENT ATTENDANCE LIST"
    ws[f"A{row}"].font = section_font
    row += 1

    headers = ["No.", "Admission No.", "Student Name", "Status", "Reason", "Parent Informed"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border
    row += 1

    for i, s in enumerate(student_rows, 1):
        ws.cell(row=row, column=1, value=i).border = thin_border
        ws.cell(row=row, column=2, value=s["admission"]).border = thin_border
        ws.cell(row=row, column=3, value=s["name"]).border = thin_border
        status_cell = ws.cell(row=row, column=4, value=s["status"])
        status_cell.border = thin_border
        if s["status"] == "Present":
            status_cell.fill = present_fill
        elif s["status"] == "Absent":
            status_cell.fill = absent_fill
        ws.cell(row=row, column=5, value=s["reason"]).border = thin_border
        informed = "Yes" if s["communicated"] == "yes" else ("No" if s["communicated"] == "no" else ("Unknown" if s["communicated"] else ""))
        ws.cell(row=row, column=6, value=informed).border = thin_border
        row += 1

    row += 1
    ws[f"A{row}"] = "ABSENTEES SUMMARY"
    ws[f"A{row}"].font = section_font
    row += 1
    if not absentees:
        ws.cell(row=row, column=1, value="No absentees today").font = normal_font
        row += 1
    else:
        for col, header in enumerate(["No.", "Admission No.", "Student Name", "Reason", "Parent Informed"], 1):
            cell = ws.cell(row=row, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
        row += 1
        for i, a in enumerate(absentees, 1):
            ws.cell(row=row, column=1, value=i).border = thin_border
            ws.cell(row=row, column=2, value=a["admission"]).border = thin_border
            ws.cell(row=row, column=3, value=a["name"]).border = thin_border
            ws.cell(row=row, column=4, value=a["reason"]).border = thin_border
            informed = "Yes" if a["communicated"] == "yes" else ("No" if a["communicated"] == "no" else "Unknown")
            ws.cell(row=row, column=5, value=informed).border = thin_border
            row += 1

    row += 1
    ws[f"A{row}"] = "CLASS ACTIVITIES (TODAY)"
    ws[f"A{row}"].font = section_font
    row += 1
    for col, header in enumerate(["No.", "Subject", "Activity Description", "Participation Notes", "Recorded By"], 1):
        cell = ws.cell(row=row, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border
    row += 1
    if not activities:
        ws.cell(row=row, column=1, value="No activities recorded for this day").font = normal_font
        row += 1
    else:
        for i, a in enumerate(activities, 1):
            ws.cell(row=row, column=1, value=i).border = thin_border
            ws.cell(row=row, column=2, value=a.subject.name if a.subject else "").border = thin_border
            ws.cell(row=row, column=3, value=a.description).border = thin_border
            ws.cell(row=row, column=4, value=a.participation_notes or "").border = thin_border
            ws.cell(row=row, column=5, value=a.recorded_by_user.full_name if a.recorded_by_user else "").border = thin_border
            row += 1

    row += 1
    ws[f"A{row}"] = "SUBJECT ATTENDANCE OVERVIEW"
    ws[f"A{row}"].font = section_font
    row += 1
    for col, header in enumerate(["No.", "Admission No.", "Student Name", "Subjects Attended", "Subjects Missed (with reason)"], 1):
        cell = ws.cell(row=row, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border
    row += 1

    if not subject_records:
        ws.cell(row=row, column=1, value="No subject attendance recorded for this day").font = normal_font
    else:
        for i, student in enumerate(students, 1):
            subjects = subject_map.get(student.id, [])
            attended = [x["subject_name"] for x in subjects if x["status"] == "present"]
            missed = [f"{x['subject_name']} ({x['reason'] or 'No reason'})" for x in subjects if x["status"] == "absent"]
            ws.cell(row=row, column=1, value=i).border = thin_border
            ws.cell(row=row, column=2, value=student.admission_number).border = thin_border
            ws.cell(row=row, column=3, value=student.full_name).border = thin_border
            ws.cell(row=row, column=4, value=", ".join(attended) if attended else "None").border = thin_border
            ws.cell(row=row, column=5, value=", ".join(missed) if missed else "None").border = thin_border
            row += 1

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 26
    ws.column_dimensions["D"].width = 35
    ws.column_dimensions["E"].width = 40
    ws.column_dimensions["F"].width = 16

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"Daily_Report_{class_obj.name.replace(' ', '_')}_{report_date}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
