// Vulnerable clipboard hijacking fixture — intercepts copy events
document.addEventListener('copy', function(e) {
    e.clipboardData.setData('text/plain', 'Malicious content injected!');
    e.preventDefault();
});

document.addEventListener('paste', function(e) {
    const pastedData = e.clipboardData.getData('text/plain');
    console.log('Intercepted paste:', pastedData);
});
