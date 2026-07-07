# Vulnerable AWS key literal fixture — AKIA pattern in source code
# This hardcoded key should be detected by the regex pattern rule

AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
config = {
    "key": "AKIAIOSFODNN7EXAMPLE",
    "region": "us-east-1"
}
