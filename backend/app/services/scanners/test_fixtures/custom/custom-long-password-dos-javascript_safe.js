// Safe Long Password DoS fixture — length check before bcrypt
const bcrypt = require('bcrypt');

async function hashPassword(password) {
    if (password.length > 72) { throw new Error('Password too long'); }
    return await bcrypt.hash(password, 10);
}

function hashPasswordSync(password) {
    if (password.length > 72) { throw new Error('Password too long'); }
    return bcrypt.hashSync(password, 10);
}

module.exports = { hashPassword, hashPasswordSync };
