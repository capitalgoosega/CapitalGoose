from fastapi import FastAPI

from app.api.routes import router

from app.db.session import Base, engine


Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="Capitol Goose Fintech API",
    version="1.0.0"
)


app.include_router(router)


@app.get("/")
def root():
    return {
        "message": "Capitol Goose Programmatic Underwriting API Running"
    }
