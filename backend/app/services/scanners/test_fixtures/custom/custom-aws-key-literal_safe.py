# Safe AWS key literal fixture — no hardcoded AKIA patterns
import os

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
config = {
    "key_source": "environment",
    "region": "us-east-1"
}
