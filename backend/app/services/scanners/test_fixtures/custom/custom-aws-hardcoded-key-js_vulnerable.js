// Vulnerable AWS hardcoded key JS fixture — string literal credentials
const AWS = require('aws-sdk');

const s3 = new AWS.S3({
    accessKeyId: "AKIAIOSFODNN7EXAMPLE",
    secretAccessKey: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
});
