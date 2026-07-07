// Safe NoSQL injection JS fixture — user input validated before query
const express = require('express');
const { MongoClient } = require('mongodb');

const app = express();
let users;

MongoClient.connect('mongodb://localhost:27017').then(client => {
    users = client.db('mydb').collection('users');
});

app.get('/find', async (req, res) => {
    // Safe: extract and validate input before using in query
    const username = String(req.query.username || '');
    const result = await users.find({username: username});
    res.json(await result.toArray());
});

app.get('/find_one', async (req, res) => {
    const email = String(req.body.email || '');
    const result = await users.findOne({email: email});
    res.json(result);
});
