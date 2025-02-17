// Fetch the current word of the day data and update the card
async function updateWOTDCard() {
    try {
        const response = await fetch('/api/wotd');
        const data = await response.json();

        // Convert date format (DD-MM-YYYY -> "Month day, year")
        const formattedDate = formatDate(data.date);

        // Update the card with the data
        const wordElement = document.getElementById('word');
        wordElement.innerHTML = `${data.word} <span id="word-type" class="word-type word-type-${data.type.toLowerCase()}">${data.type}</span>`;
        const ipaElement = document.getElementById('ipa');
        ipaElement.innerHTML = `${data.ipa} <span><img src="assets/svgs/pronunciation.svg" alt="Pronunciation" class="pronunciation"></span>`;
        document.getElementById('definition').textContent = data.definition
        document.getElementById('date').textContent = formattedDate    
    } catch (error) {
        console.error('Error fetching WOTD:', error);
    }
}

// Convert date format (DD-MM-YYYY -> "Month day, year")
function formatDate(date) {
    const months = [
        'January', 'February', 'March', 'April', 'May', 'June', 
        'July', 'August', 'September', 'October', 'November', 'December'
    ];

    const [day, month, year] = date.split('-');
    const dateNumber = parseInt(day, 10);
    const suffix = getDateSuffix(dateNumber);

    return `${months[parseInt(month) - 1]} ${dateNumber}${suffix}, ${year}`;
}

// Get the date suffix (e.g., 1 -> "st", 2 -> "nd", etc.)
function getDateSuffix(day) {
    if (day >= 11 && day <= 13) return 'th';
    switch (day % 10) {
        case 1: return 'st';
        case 2: return 'nd';
        case 3: return 'rd';
        default: return 'th';
    }
}

// Call the function to update the WOTD card when the page loads
document.addEventListener('DOMContentLoaded', updateWOTDCard);