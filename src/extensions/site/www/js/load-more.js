function attachLoadMoreListener() {
    document.getElementById('load-more-button').addEventListener('click', async function () {
        const container = this.parentElement.parentElement;

        // Remove the current load-more-button
        this.parentElement.remove();

        // Get the date from the last WOTD card (fix this in v1.3.0, this is a horrible system)
        const wotdCards = document.querySelectorAll('.wotd-card');
        if (wotdCards.length === 0) {
            // If no cards exist yet, use current date as fallback
            const currentDate = new Date();
            var formattedDate = `${String(currentDate.getDate()).padStart(2, '0')}-${String(currentDate.getMonth() + 1).padStart(2, '0')}-${currentDate.getFullYear()}`;
        } else {
            const lastCard = wotdCards[wotdCards.length - 1];
            const dateElement = lastCard.querySelector('.date');
            const readableDate = dateElement.textContent;
            
            // Remove the suffix (st, nd, rd, th) from the day
            const cleanDate = readableDate.replace(/(\d+)(st|nd|rd|th)/, '$1');
            
            // Parse the date
            const dateObject = new Date(cleanDate);
            
            // Format to dd-mm-yyyy
            const day = String(dateObject.getDate()).padStart(2, '0');
            const month = String(dateObject.getMonth() + 1).padStart(2, '0');
            const year = dateObject.getFullYear();
            var formattedDate = `${day}-${month}-${year}`;
        }

        try {
            // Fetch data from the API
            const response = await fetch(`/api/query_previous?date=${formattedDate}`);
            const { has_more, results } = await response.json();

            // Generate cards for the fetched data
            let cardsHTML = '';
            results.forEach(wotd => {
            // Use the date directly from the API
            const dateParts = wotd.date.split('-');
            const day = parseInt(dateParts[0], 10);
            const month = parseInt(dateParts[1], 10) - 1;
            const year = parseInt(dateParts[2], 10);

            const date = new Date(Date.UTC(year, month, day, 12, 0, 0));
            
            const options = { year: 'numeric', month: 'long', day: 'numeric' };
            const suffix = ['th', 'st', 'nd', 'rd'][(day % 10 === 1 && day % 100 !== 11) ? 1 : (day % 10 === 2 && day % 100 !== 12) ? 2 : (day % 10 === 3 && day % 100 !== 13) ? 3 : 0];
            const formattedDate = date.toLocaleDateString('en-US', options).replace(/\b\d{1,2}\b/, day + suffix);

            cardsHTML += `
                <section class="card wotd-card">
                <h1 id="word" class="word">
                    ${wotd.word}
                    <span id="pos" class="pos pos-${wotd.pos.toLowerCase()}">${wotd.pos}</span>
                </h1>
                <p id="ipa" class="ipa">${wotd.ipa}</p>
                <p id="definition" class="definition">
                    ${wotd.definition}
                </p>
                <p id="date" class="date">${formattedDate}</p>
                </section>
            `;
            });

            // Append the new cards
            container.innerHTML += cardsHTML;

            // If there are more words to load, append a new load-more-button
            if (has_more) {
            container.innerHTML += `
                <section class="load-more">
                <button id="load-more-button" class="load-more-button">Load More</button>
                </section>
            `;

            // Reattach the listener to the new load-more-button
            attachLoadMoreListener();
            }
        } catch (error) {
            console.error('Error fetching data:', error);
        }
    });
}

attachLoadMoreListener();
