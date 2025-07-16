from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import uuid
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

# Constants for JWT
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Database setup (SQLite for demo)
SQLALCHEMY_DATABASE_URL = "sqlite:///./audit.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Audit log model
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    action = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# User model for demo
fake_users_db = {
    "admin": {
        "username": "admin",
        "full_name": "Admin User",
        "hashed_password": "$2b$12$KIXQ1q6v6q6q6q6q6q6q6u6q6q6q6q6q6q6q6q6q6q6q6q6q6q6q6",  # password: secret
        "disabled": False,
    }
}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()

OUTPUT_DIR = "generated_pdfs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

class User(BaseModel):
    username: str
    full_name: str | None = None
    disabled: bool | None = None

class UserInDB(User):
    hashed_password: str

def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)

def authenticate_user(db, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, username)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def log_action(db_session, username: str, action: str):
    log = AuditLog(username=username, action=action)
    db_session.add(log)
    db_session.commit()

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/upload/")
async def upload_pdf(file: UploadFile = File(...), current_user: User = Depends(get_current_active_user)):
    temp_filename = f"temp_{uuid.uuid4()}.pdf"
    with open(temp_filename, "wb") as f:
        f.write(await file.read())

    extracted_text = ""
    try:
        with pdfplumber.open(temp_filename) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    extracted_text += text + "\n"
    finally:
        os.remove(temp_filename)

    # Log action
    db = SessionLocal()
    log_action(db, current_user.username, "Uploaded PDF and extracted text")
    db.close()

    return {"extracted_text": extracted_text.strip()}

@app.post("/generate/")
async def generate_fir(
    fir_no: str = Form(...),
    victim_name: str = Form(...),
    fraud_amount: str = Form(...),
    complaint_text: str = Form(...),
    current_user: User = Depends(get_current_active_user)
):
    output_filename = f"{OUTPUT_DIR}/FIR_{uuid.uuid4()}.pdf"

    c = canvas.Canvas(output_filename, pagesize=A4)
    width, height = A4

    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, f"FIR No.: {fir_no}")
    y -= 30

    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"Victim Name: {victim_name}")
    y -= 20
    c.drawString(50, y, f"Fraud Amount: {fraud_amount}")
    y -= 40

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Complaint Details:")
    y -= 20

    c.setFont("Helvetica", 11)
    for line in complaint_text.split("\n"):
        if y < 50:
            c.showPage()
            y = height - 50
        c.drawString(50, y, line.strip())
        y -= 15

    c.save()

    # Log action
    db = SessionLocal()
    log_action(db, current_user.username, f"Generated FIR PDF {output_filename}")
    db.close()

    return {"download_link": f"/download/{os.path.basename(output_filename)}"}

@app.get("/download/{filename}")
async def download_file(filename: str, current_user: User = Depends(get_current_active_user)):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=filename, media_type='application/pdf')
    else:
        return {"error": "File not found"}
