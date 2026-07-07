// Safe ReDoS fixture — no nested quantifiers
const userInput = process.argv[2] || '';

// Safe: simple pattern without nested quantifiers
const safePattern = new RegExp('^[a-zA-Z0-9]+$');
const result = safePattern.test(userInput);

console.log(result);
