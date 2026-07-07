// Safe clipboard fixture — uses standard Clipboard API with explicit user action
const copyButton = document.getElementById('copy-btn');

copyButton.addEventListener('click', function() {
    const contentEl = document.getElementById('content');
    const text = contentEl.textContent;
    navigator.clipboard.writeText(text).then(function() {
        console.log('Content copied to clipboard');
    });
});
