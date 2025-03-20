// Automatically scroll to the bottom of the log
const log = document.getElementById('log');
log.scrollTop = log.scrollHeight;

// Clear input field after submitting
const inputField = document.querySelector('input[name="command"]');
inputField.value = '';