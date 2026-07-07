# Vulnerable ReDoS fixture — nested quantifiers cause catastrophic backtracking
import re

# Nested quantifier: (a+)+ causes exponential backtracking
evil_pattern = re.compile(r'(a+)+$')

text = input("Enter text: ")
result = re.match(r'(a+)+$', text)

result2 = re.search(r'(.*)*something', text)
