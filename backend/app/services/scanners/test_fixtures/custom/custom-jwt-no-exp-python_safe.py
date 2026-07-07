# Safe JWT fixture — token created with expiration claim
import jwt
import datetime

payload = {"user_id": 123, "role": "admin", "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}
token = jwt.encode(payload, "secret", algorithm="HS256")
print(token)
