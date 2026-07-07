// Vulnerable NoSQL injection JS fixture — user input directly in query
const express = require('express');
const { MongoClient } = require('mongodb');

const app = express();
let users;

MongoClient.connect('mongodb://localhost:27017').then(client => {
    users = client.db('mydb').collection('users');
});

app.get('/find', async (req, res) => {
    const result = await users.find({username: req.query.username});
    res.json(await result.toArray());
});

app.get('/find_one', async (req, res) => {
    const result = await users.findOne({email: req.body.email});
    res.json(result);
});
