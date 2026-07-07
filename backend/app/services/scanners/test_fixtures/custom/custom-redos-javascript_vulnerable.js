// Vulnerable ReDoS fixture — nested quantifiers in JS regex
const userInput = process.argv[2] || '';

// Nested quantifier: (a+)+ causes catastrophic backtracking
const evilPattern = new RegExp('(a+)+$');
const result = evilPattern.test(userInput);

console.log(result);
