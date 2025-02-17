document.addEventListener('DOMContentLoaded', function () {
    function updateCountdown() {
        const countdownElement = document.getElementById('countdown');
        
        // Target time: 8:00 AM PST
        const now = new Date();
        const target = new Date();
        target.setUTCHours(16, 0, 0, 0); // 8:00 AM PST = 16:00 UTC

        // If the target time has already passed today, set it for tomorrow
        if (now > target) {
            target.setUTCDate(target.getUTCDate() + 1);
        }

        const diff = target - now;
        const hours = String(Math.floor(diff / (1000 * 60 * 60))).padStart(2, '0');
        const minutes = String(Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))).padStart(2, '0');
        const seconds = String(Math.floor((diff % (1000 * 60)) / 1000)).padStart(2, '0');

        countdownElement.textContent = `${hours}:${minutes}:${seconds}`;
    }

    // Update countdown every second
    setInterval(updateCountdown, 1000);
    updateCountdown(); // Run immediately so there's no delay
});