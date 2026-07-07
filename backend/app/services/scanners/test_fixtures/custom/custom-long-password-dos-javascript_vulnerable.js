// Vulnerable Long Password DoS fixture — no length check before bcrypt
const bcrypt = require('bcrypt');

async function hashPassword(password) {
    return await bcrypt.hash(password, 10);
}

function hashPasswordSync(password) {
    return bcrypt.hashSync(password, 10);
}

module.exports = { hashPassword, hashPasswordSync };
