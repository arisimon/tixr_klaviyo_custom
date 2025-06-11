from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from app.core.config import settings
from app.core.logging import get_logger
import os

logger = get_logger(__name__)

# Create SQLAlchemy engine with Supabase connection
def create_database_engine():
    """Create database engine with Supabase-optimized settings."""
    
    # Use Supabase connection string from environment
    database_url = settings.database_url
    
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required for Supabase connection")
    
    # Ensure SSL is enabled for Supabase connections
    if "sslmode" not in database_url:
        if "?" in database_url:
            database_url += "&sslmode=require"
        else:
            database_url += "?sslmode=require"
    
    engine = create_engine(
        database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,  # Verify connections before use
        pool_recycle=3600,   # Recycle connections every hour
        echo=settings.debug,  # Log SQL queries in debug mode
        connect_args={
            "sslmode": "require",
            "connect_timeout": 30,
            "application_name": f"{settings.app_name}-{settings.environment}"
        }
    )
    
    logger.info("Database engine created", 
               pool_size=settings.database_pool_size,
               max_overflow=settings.database_max_overflow)
    
    return engine

# Create engine instance
engine = create_database_engine()

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create declarative base
Base = declarative_base()

def get_db_session() -> Session:
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_db():
    """Context manager for database sessions."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Database transaction failed", error=str(e))
        raise
    finally:
        db.close()

def init_database():
    """Initialize database tables."""
    try:
        # Import all models to ensure they're registered
        from app.models import database
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        
        logger.info("Database tables initialized successfully")
        
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise

def check_database_connection():
    """Check if database connection is working."""
    try:
        with engine.connect() as connection:
            result = connection.execute("SELECT 1")
            result.fetchone()
        
        logger.info("Database connection verified")
        return True
        
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        return False

def get_database_info():
    """Get database connection information for monitoring."""
    try:
        with engine.connect() as connection:
            # Get database version
            version_result = connection.execute("SELECT version()")
            version = version_result.fetchone()[0]
            
            # Get connection count
            conn_result = connection.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
            )
            connection_count = conn_result.fetchone()[0]
            
            return {
                "status": "connected",
                "version": version,
                "connection_count": connection_count,
                "pool_size": settings.database_pool_size,
                "max_overflow": settings.database_max_overflow
            }
            
    except Exception as e:
        logger.error("Failed to get database info", error=str(e))
        return {
            "status": "error",
            "error": str(e)
        }

