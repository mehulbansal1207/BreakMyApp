// Vulnerable JWT no-exp JS fixture — jwt.sign without expiresIn option
const jwt = require('jsonwebtoken');

const payload = { user_id: 123, role: 'admin' };
const token = jwt.sign(payload, 'secret');
console.log(token);
