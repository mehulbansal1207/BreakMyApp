// Safe JWT JS fixture — jwt.sign with expiresIn option
const jwt = require('jsonwebtoken');

const payload = { user_id: 123, role: 'admin' };
const token = jwt.sign(payload, 'secret', { expiresIn: '1h' });
console.log(token);
