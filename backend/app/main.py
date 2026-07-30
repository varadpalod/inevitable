import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.api import auth, commands, logs
from app.models.models import User
from app.core.security import get_password_hash

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set CORS origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development, we allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(commands.router, prefix=f"{settings.API_V1_STR}/commands", tags=["commands"])
app.include_router(logs.router, prefix=f"{settings.API_V1_STR}/logs", tags=["logs"])

@app.on_event("startup")
def create_default_user():
    """
    Seed a default user for testing and demo purposes.
    """
    db = SessionLocal()
    try:
        default_user = db.query(User).filter(User.username == "admin").first()
        if not default_user:
            logger.info("Creating default demo user 'admin'...")
            user = User(
                username="admin",
                hashed_password=get_password_hash("admin123"),
                pin="1234"
            )
            db.add(user)
            db.commit()
            logger.info("Default user created. Username: admin, Password: admin123, PIN: 1234")
    except Exception as e:
        logger.error(f"Error seeding default user: {e}")
    finally:
        db.close()

@app.get("/")
def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME} API (v1.0)"}
