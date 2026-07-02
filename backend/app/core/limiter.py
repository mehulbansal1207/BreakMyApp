import redis.asyncio as aioredis
from fastapi import HTTPException
from app.core.config import settings

async def check_rate_limit(
    identifier: str,
    key_prefix: str = "ratelimit",
    limit: int = 5,
    window_seconds: int = 3600,
) -> None:
    """
    Checks if the identifier has exceeded the rate limit.

    Args:
        identifier: The unique key to rate-limit (e.g. IP address, user ID).
        key_prefix: Redis key prefix (e.g. "ratelimit", "ratelimit:issues").
        limit: Maximum number of allowed requests within the window.
        window_seconds: Duration of the sliding window in seconds.
    """
    client = aioredis.from_url(settings.REDIS_URL)
    try:
        key = f"{key_prefix}:{identifier}"
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window_seconds)
            
        if count > limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {limit} requests per {window_seconds // 60} minutes."
            )
    finally:
        await client.close()
