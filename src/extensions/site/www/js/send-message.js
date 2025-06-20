// send-message.js

function sendMessage() {
    // Get form values
    const name = document.getElementById('name').value.trim();
    const email = document.getElementById('email').value.trim();
    const subject = document.getElementById('subject').value.trim();
    const message = document.getElementById('message').value.trim();

    // Validate required fields
    if (!email || !subject || !message) {
        alert('Please fill out all required fields.');
        return;
    }

    // Create the payload
    const payload = {
        name: name,
        email: email,
        subject: subject,
        message: message
    };

    // Check payload size
    const payloadSize = new Blob([JSON.stringify(payload)]).size; // Size in bytes
    const maxSize = 1024 * 1024; // 1MB in bytes

    if (payloadSize > maxSize) {
        alert('Message is too large to send. Please reduce the size of your input.');
        return;
    }

    // Send the data using Fetch API
    fetch('/api/send-message', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    })
    .then(response => {
        if (response.ok) {
            document.querySelector('.contact-form').reset();
            alert('Message sent successfully!');
        } else {
            alert('Failed to send message. Please try again later.');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred while sending the message.');
    });
}