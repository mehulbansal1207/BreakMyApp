import redis.asyncio as aioredis
from fastapi import HTTPException
from app.core.config import settings

async def check_rate_limit(ip: str) -> None:
    """
    Checks if the IP address has exceeded the rate limit of 5 scans per hour.
    """
    client = aioredis.from_url(settings.REDIS_URL)
    try:
        key = f"ratelimit:{ip}"
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, 3600)
            
        if count > 5:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Maximum 5 scans per hour per IP address."
            )
    finally:
        await client.close()
