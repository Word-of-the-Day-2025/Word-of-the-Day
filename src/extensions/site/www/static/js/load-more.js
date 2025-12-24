function attachLoadMoreListener() {
    document.getElementById('load-more-button').addEventListener('click', async function () {
        const container = this.parentElement;

        // Remove the current load-more-button
        this.remove();

        // Get the date from the last WOTD card using the data-date attribute
        const wotdCards = document.querySelectorAll('.wotd-card');
        let formattedDate;
        
        if (wotdCards.length === 0) {
            // If no cards exist yet, use current date as fallback
            const currentDate = new Date();
            formattedDate = `${currentDate.getFullYear()}-${String(currentDate.getMonth() + 1).padStart(2, '0')}-${String(currentDate.getDate()).padStart(2, '0')}`;
        } else {
            const lastCard = wotdCards[wotdCards.length - 1];
            const dateElement = lastCard.querySelector('.wotd-date');
            // Get the data-date attribute, which contains the YYYY-MM-DD format
            formattedDate = dateElement.getAttribute('data-date') || dateElement.textContent.trim();
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
                const year = parseInt(dateParts[0], 10);
                const month = parseInt(dateParts[1], 10) - 1;
                const day = parseInt(dateParts[2], 10);

                const date = new Date(Date.UTC(year, month, day, 12, 0, 0));
                
                const options = { year: 'numeric', month: 'long', day: 'numeric' };
                const suffix = ['th', 'st', 'nd', 'rd'][(day % 10 === 1 && day % 100 !== 11) ? 1 : (day % 10 === 2 && day % 100 !== 12) ? 2 : (day % 10 === 3 && day % 100 !== 13) ? 3 : 0];
                const formattedDateDisplay = date.toLocaleDateString('en-US', options).replace(/\b\d{1,2}\b/, day + suffix);

                cardsHTML += `
                    <section class="card wotd-card">
                        <div class="wotd-header">
                            <span class="wotd-word">${wotd.word.charAt(0).toUpperCase() + wotd.word.slice(1)}</span>
                            <span class="wotd-ipa">${wotd.ipa}</span>
                            <span class="wotd-pos wotd-pos-${wotd.pos.toLowerCase()}">${wotd.pos}</span>
                        </div>
                        <p class="wotd-definition">${wotd.definition}</p>
                        <p class="wotd-date" data-date="${wotd.date}">${formattedDateDisplay}</p>
                    </section>
                `;
            });

            // Append the new cards
            container.innerHTML += cardsHTML;

            // If there are more words to load, append a new load-more-button
            if (has_more) {
                container.innerHTML += `
                    <button id="load-more-button" class="button load-more-button">Load More</button>
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