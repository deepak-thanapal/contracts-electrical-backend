from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import os
import re
import json
from datetime import datetime
from typing import Optional, List

app = FastAPI()

# ---------------------
# CORS
# ---------------------
origins = [
    "https://contracts-electrical.azurewebsites.net",
    "http://localhost:8080"  # replace with your frontend domain
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------
# File Setup
# ---------------------
EXCEL_FILE = "data/users.xlsx"
PROJECTS_DIR = "data/projects"

os.makedirs("data", exist_ok=True)
os.makedirs(PROJECTS_DIR, exist_ok=True)

if not os.path.exists(EXCEL_FILE):
    df = pd.DataFrame(columns=["username", "first_name", "password", "role"])
    df.to_excel(EXCEL_FILE, index=False)

# ---------------------
# Request Schemas
# ---------------------
class SignupRequest(BaseModel):
    username: str  # email or phone
    first_name: str
    password: str
    role: str = "user"  # default role is "user"

class LoginRequest(BaseModel):
    username: str
    password: str

class ProgressUpdate(BaseModel):
    updateId: str
    projectCode: str
    sectionId: str
    itemCode: str 
    date: datetime
    supervisorId: str
    supervisorName: Optional[str]
    workDoneQty: float
    unit: Optional[str]
    remarks: Optional[str] 
    verifiedBy: Optional[str]
    attachments: Optional[List[str]]
    status: str = "submitted"

class Project(BaseModel):
    title: str
    location: str
    supervisors: list[str]  # phone numbers
    projectCode: str
    description: str | None = None
    totalLabourCost: str | None = None
    averageLabourCost: str | None = None
    numberOfSupervisors: str | None = None
    numberOfLabours: str | None = None
    totalCTC: str | None = None
    sections: list
    totals: dict
    createdate: str
    lastModified: str | None = None
    status: str = "active"
    completedCost: float = 0
    progressUpdates: List[ProgressUpdate] = []

# ---------------------
# Helpers
# ---------------------
def is_valid_email(username: str) -> bool:
    try:
        EmailStr.validate(username)
        return True
    except:
        return False

def is_valid_phone(username: str) -> bool:
    return re.fullmatch(r"^\+?\d{10,15}$", username) is not None

def load_users():
    return pd.read_excel(EXCEL_FILE)

def save_users(df):
    df.to_excel(EXCEL_FILE, index=False)

def load_projects():
    projects = []
    for file in os.listdir(PROJECTS_DIR):
        if file.endswith(".json"):
            with open(os.path.join(PROJECTS_DIR, file), "r", encoding="utf-8") as f:
                try:
                    projects.append(json.load(f))
                except:
                    continue
    return projects

def load_projects_with_file():
    projects = []
    for file in os.listdir(PROJECTS_DIR):
        if file.endswith(".json"):
            file_path = os.path.join(PROJECTS_DIR, file)
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    data["__file"] = file
                    projects.append(data)
                except Exception as e:
                    print(f"Skipping {file}: {e}")
                    continue
    return projects


# ---------------------
# Signup API
# ---------------------
@app.post("/signup")
def signup(req: SignupRequest):
    if not (is_valid_email(req.username) or is_valid_phone(req.username)):
        raise HTTPException(status_code=400, detail="Username must be a valid email or phone number")

    df = load_users()

    if req.username in df["username"].values:
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = {
        "username": req.username,
        "first_name": req.first_name,
        "password": req.password,  # ⚠️ plain password
        "role": req.role,
    }

    df = pd.concat([df, pd.DataFrame([new_user])], ignore_index=True)
    save_users(df)

    return {
        "message": "User created successfully",
        "username": req.username,
        "first_name": req.first_name,
        "role": req.role,
    }

# ---------------------
# Login API
# ---------------------
@app.post("/login")
def login(req: LoginRequest):
    df = load_users()

    user = df[(df["username"] == req.username) & (df["password"] == req.password)]
    if user.empty:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    role = user.iloc[0]["role"]
    return {"success": True, "role": role, "username": req.username}

# ---------------------
# Save Project API
# ---------------------
@app.post("/projects")
def save_project(project: Project):
    file_name = f"{PROJECTS_DIR}/{project.projectCode}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"

    project_data = project.dict()
    project_data["createdate"] = datetime.now().isoformat()
    project_data["lastModified"] = datetime.now().isoformat()

    project_data.setdefault("completedCost", 0)
    project_data.setdefault("progressUpdates", [])

    try:
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(project_data, f, indent=4)

        return {"message": "Project saved successfully", "file": file_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------
# Get Projects API
# ---------------------
@app.get("/projects")
def get_projects(username: Optional[str] = None, role: str = "user"):
    projects = load_projects()
    users_df = load_users()

    # Build lookup dict: {username -> first_name}
    user_lookup = dict(zip(users_df["username"], users_df["first_name"]))

    # Replace supervisor phone numbers with first names if available
    for project in projects:
        supervisors = project.get("supervisors", [])
        if isinstance(supervisors, list):
            project["supervisors_first_names"] = [
                user_lookup.get(s, s) for s in supervisors
            ]  # fallback to phone if not found
        else:
            project["supervisors_first_names"] = []

    print(username, role)
    if role == "admin":
        return projects
    else:
        if not username:
            return []
        print([p for p in projects if username in p.get("supervisors", [])])
        return [p for p in projects if username in p.get("supervisors", [])]


# ---------------------
# Get Single Project API
# ---------------------
@app.get("/projects/{project_id}")
def get_project(project_id: str):
    print(project_id)
    projects = load_projects_with_file()
    for project in projects:
        file_stem = os.path.splitext(project["__file"])[0]
        if file_stem.startswith(project_id):
            return project
    raise HTTPException(status_code=404, detail="Project not found")

# ---------------------
# Delete Project API
# ---------------------
@app.delete("/projects/{project_id}")
def delete_project(project_id: str, role: str, username: Optional[str] = None):
    if role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete projects")

    projects = load_projects_with_file()
    for project in projects:
        file_stem = os.path.splitext(project["__file"])[0]
        if file_stem.startswith(project_id):  # ✅ match project ID with filename
            file_path = os.path.join(PROJECTS_DIR, project["__file"])
            try:
                os.remove(file_path)
                return {"message": f"Project {project_id} deleted successfully"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to delete project: {e}")

    raise HTTPException(status_code=404, detail="Project not found")

# ---------------------
# Update Project API
# ---------------------
@app.put("/projects/{project_id}")
def update_project(project_id: str, updated: Project):
    projects = load_projects_with_file()
    target_file = None

    for project in projects:
        file_stem = os.path.splitext(project["__file"])[0]
        if file_stem.startswith(project_id):
            target_file = os.path.join(PROJECTS_DIR, project["__file"])
            break

    if not target_file:
        raise HTTPException(status_code=404, detail="Project not found")

    project_data = updated.dict()
    project_data["lastModified"] = datetime.now().isoformat()

    try:
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(project_data, f, indent=4)
        return {"message": f"Project {project_id} updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update project: {e}")
