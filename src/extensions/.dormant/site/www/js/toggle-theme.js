function toggleTheme() {
    // Check the current theme from the data-theme attribute
    const currentTheme = document.body.getAttribute('data-theme');

    // Toggle between light and dark theme
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.body.setAttribute('data-theme', newTheme);

    // Save the user's theme preference in localStorage
    localStorage.setItem('theme', newTheme);

    // Update the image source for the theme icon
    const themeToggleIcon = document.getElementById('theme-toggle');
    if (newTheme === 'dark') {
        themeToggleIcon.src = 'assets/svgs/dark-theme.svg'; // Dark mode icon
        themeToggleIcon.alt = 'Dark Mode';  // Update alt text
    } else {
        themeToggleIcon.src = 'assets/svgs/light-theme.svg'; // Light mode icon
        themeToggleIcon.alt = 'Light Mode'; // Update alt text
    }
}

// Check and apply the saved theme when the page loads
window.onload = function() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        document.body.setAttribute('data-theme', savedTheme);
    } else {
        // Default to light theme if no preference is saved
        document.body.setAttribute('data-theme', 'light');
    }

    // Update the theme icon based on the saved theme
    const themeToggleIcon = document.getElementById('theme-toggle');
    if (savedTheme === 'dark') {
        themeToggleIcon.src = 'assets/svgs/dark-theme.svg';
        themeToggleIcon.alt = 'Dark Mode';
    } else {
        themeToggleIcon.src = 'assets/svgs/light-theme.svg';
        themeToggleIcon.alt = 'Light Mode';
    }
};