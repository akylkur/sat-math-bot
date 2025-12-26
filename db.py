"""
Database module for analytics.
Uses asyncpg for async PostgreSQL operations.
All functions are safe: if DB is unavailable, they fail silently.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import asyncpg
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def init_db():
    """Initialize database connection pool."""
    global _pool
    if _pool:
        return
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL not found. Analytics will be disabled.")
        return
    
    try:
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=1,
            max_size=5,
            command_timeout=5
        )
        logger.info("Database connection pool created.")
    except Exception as e:
        logger.error(f"Failed to create database pool: {e}")
        _pool = None


async def close_db():
    """Close database connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed.")


@asynccontextmanager
async def get_conn():
    """Get database connection from pool. Safe wrapper."""
    if not _pool:
        yield None
        return
    
    try:
        async with _pool.acquire() as conn:
            yield conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        yield None


async def ensure_user(user_id: int, username: Optional[str] = None, 
                     first_name: Optional[str] = None, 
                     last_name: Optional[str] = None) -> bool:
    """Ensure user exists in database. Returns True if successful."""
    async with get_conn() as conn:
        if not conn:
            return False
        
        try:
            await conn.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    username = COALESCE(EXCLUDED.username, users.username),
                    first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                    last_name = COALESCE(EXCLUDED.last_name, users.last_name),
                    updated_at = NOW()
                """,
                user_id, username, first_name, last_name
            )
            return True
        except Exception as e:
            logger.error(f"Error ensuring user {user_id}: {e}")
            return False


async def log_event(user_id: int, event_type: str, metadata: Optional[Dict] = None) -> bool:
    """Log an event. Returns True if successful."""
    async with get_conn() as conn:
        if not conn:
            return False
        
        try:
            await ensure_user(user_id)
            await conn.execute(
                """
                INSERT INTO events (user_id, event_type, metadata)
                VALUES ($1, $2, $3)
                """,
                user_id, event_type, metadata or {}
            )
            return True
        except Exception as e:
            logger.error(f"Error logging event {event_type} for user {user_id}: {e}")
            return False


async def log_attempt(user_id: int, question_id: str, question_num: Optional[str],
                     user_answer: str, correct_answer: str, is_correct: bool,
                     difficulty: Optional[str] = None, topic: Optional[str] = None) -> bool:
    """Log a question attempt. Returns True if successful."""
    async with get_conn() as conn:
        if not conn:
            return False
        
        try:
            await ensure_user(user_id)
            await conn.execute(
                """
                INSERT INTO attempts (user_id, question_id, question_num, user_answer, 
                                    correct_answer, is_correct, difficulty, topic)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                user_id, question_id, question_num, user_answer, 
                correct_answer, is_correct, difficulty, topic
            )
            return True
        except Exception as e:
            logger.error(f"Error logging attempt for user {user_id}: {e}")
            return False


# Analytics queries

async def get_dau_today(timezone_offset: int = 6) -> int:
    """Get Daily Active Users for today (UTC+6)."""
    async with get_conn() as conn:
        if not conn:
            return 0
        
        try:
            # Calculate start of day in UTC+6
            now = datetime.utcnow()
            tz_offset = timedelta(hours=timezone_offset)
            local_now = now + tz_offset
            start_of_day = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            start_of_day_utc = start_of_day - tz_offset
            
            count = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM events
                WHERE created_at >= $1
                """,
                start_of_day_utc
            )
            return count or 0
        except Exception as e:
            logger.error(f"Error getting DAU: {e}")
            return 0


async def get_attempts_today(timezone_offset: int = 6) -> int:
    """Get attempts count for today (UTC+6)."""
    async with get_conn() as conn:
        if not conn:
            return 0
        
        try:
            now = datetime.utcnow()
            tz_offset = timedelta(hours=timezone_offset)
            local_now = now + tz_offset
            start_of_day = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            start_of_day_utc = start_of_day - tz_offset
            
            count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM attempts
                WHERE created_at >= $1
                """,
                start_of_day_utc
            )
            return count or 0
        except Exception as e:
            logger.error(f"Error getting attempts today: {e}")
            return 0


async def get_attempts_total() -> int:
    """Get total attempts count (all-time)."""
    async with get_conn() as conn:
        if not conn:
            return 0
        
        try:
            count = await conn.fetchval("SELECT COUNT(*) FROM attempts")
            return count or 0
        except Exception as e:
            logger.error(f"Error getting total attempts: {e}")
            return 0


async def get_accuracy() -> float:
    """Get overall accuracy (correct / total)."""
    async with get_conn() as conn:
        if not conn:
            return 0.0
        
        try:
            result = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as correct
                FROM attempts
                """
            )
            if result and result['total'] > 0:
                return (result['correct'] / result['total']) * 100
            return 0.0
        except Exception as e:
            logger.error(f"Error getting accuracy: {e}")
            return 0.0


async def get_attempts_per_day(days: int = 14, timezone_offset: int = 6) -> List[Tuple[str, int]]:
    """Get attempts per day for last N days. Returns list of (date, count) tuples."""
    async with get_conn() as conn:
        if not conn:
            return []
        
        try:
            now = datetime.utcnow()
            tz_offset = timedelta(hours=timezone_offset)
            local_now = now + tz_offset
            start_date = local_now - timedelta(days=days)
            start_date_utc = start_date - tz_offset
            
            rows = await conn.fetch(
                f"""
                SELECT 
                    DATE(created_at + INTERVAL '{timezone_offset} hours') as date,
                    COUNT(*) as count
                FROM attempts
                WHERE created_at >= $1
                GROUP BY DATE(created_at + INTERVAL '{timezone_offset} hours')
                ORDER BY date DESC
                """,
                start_date_utc
            )
            
            return [(row['date'].strftime('%Y-%m-%d'), row['count']) for row in rows]
        except Exception as e:
            logger.error(f"Error getting attempts per day: {e}")
            return []


async def get_top_users_last_7_days(limit: int = 10, timezone_offset: int = 6) -> List[Tuple[int, int]]:
    """Get top users by solved questions in last 7 days. Returns list of (user_id, count) tuples."""
    async with get_conn() as conn:
        if not conn:
            return []
        
        try:
            now = datetime.utcnow()
            tz_offset = timedelta(hours=timezone_offset)
            local_now = now + tz_offset
            start_date = local_now - timedelta(days=7)
            start_date_utc = start_date - tz_offset
            
            rows = await conn.fetch(
                """
                SELECT user_id, COUNT(*) as count
                FROM attempts
                WHERE created_at >= $1 AND is_correct = true
                GROUP BY user_id
                ORDER BY count DESC
                LIMIT $2
                """,
                start_date_utc, limit
            )
            
            return [(row['user_id'], row['count']) for row in rows]
        except Exception as e:
            logger.error(f"Error getting top users: {e}")
            return []


async def get_retention_d1() -> float:
    """Get D1 retention: % of users who returned the next day."""
    async with get_conn() as conn:
        if not conn:
            return 0.0
        
        try:
            result = await conn.fetchrow(
                """
                WITH first_visits AS (
                    SELECT user_id, DATE(MIN(created_at)) as first_date
                    FROM events
                    WHERE event_type = 'user_start'
                    GROUP BY user_id
                ),
                returned_users AS (
                    SELECT DISTINCT fv.user_id
                    FROM first_visits fv
                    INNER JOIN events e ON e.user_id = fv.user_id
                    WHERE DATE(e.created_at) = fv.first_date + INTERVAL '1 day'
                )
                SELECT 
                    COUNT(DISTINCT fv.user_id) as total_users,
                    COUNT(DISTINCT ru.user_id) as returned_users
                FROM first_visits fv
                LEFT JOIN returned_users ru ON ru.user_id = fv.user_id
                """
            )
            
            if result and result['total_users'] > 0:
                return (result['returned_users'] / result['total_users']) * 100
            return 0.0
        except Exception as e:
            logger.error(f"Error getting retention D1: {e}")
            return 0.0

