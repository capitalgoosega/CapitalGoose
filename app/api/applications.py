from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.application import Application

router = APIRouter()

@router.get("/")
def get_all(db: Session = Depends(get_db)):
    return db.query(Application).all()
