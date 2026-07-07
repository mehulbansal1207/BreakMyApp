# Vulnerable JWT no-exp fixture — token created without expiration claim
import jwt

payload = {"user_id": 123, "role": "admin"}
token = jwt.encode(payload, "secret", algorithm="HS256")
print(token)
