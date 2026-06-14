import psycopg2
from psycopg2.extras import RealDictCursor
from app.config import settings

def get_connection():
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        cursor_factory=RealDictCursor,
    )

def fetch_all(query: str, params: tuple = ()): 
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

def fetch_one(query: str, params: tuple = ()): 
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()

def execute(query: str, params: tuple = ()): 
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            conn.commit()

def execute_returning(query: str, params: tuple = ()): 
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            conn.commit()
            return row
