// Get URL parameters
const urlParams = new URLSearchParams(window.location.search);
const adminPassword = urlParams.get('password');

// Get form and inputs
const form = document.querySelector('form');

const wordInput = document.getElementById('word-input');
const ipaInput = document.getElementById('ipa-input');
const posInput = document.getElementById('pos-input');
const definitionInput = document.getElementById('definition-input');

// Handle form submission
form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const payload = {
        word: wordInput.value.trim(),
        ipa: ipaInput.value.trim(),
        pos: posInput.value.trim(),
        definition: definitionInput.value.trim(),
        admin_password: adminPassword
    };

    try {
        const response = await fetch('/api/admin/append_word', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            alert('Word appended successfully!');

            // Clear form after success
            wordInput.value = '';
            ipaInput.value = '';
            posInput.value = '';
            definitionInput.value = '';
        } else {
            alert('Failed to append word: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error appending WOTD entry:', error);
        alert('An error occurred while appending the word.');
    }
});
