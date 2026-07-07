# Safe ReDoS fixture — no nested quantifiers, safe regex patterns
import re

# Safe: simple character class with single quantifier, no nesting
email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

text = input("Enter email: ")
result = re.match(r'^[a-zA-Z0-9]+$', text)

result2 = re.search(r'\d{3}-\d{3}-\d{4}', text)
