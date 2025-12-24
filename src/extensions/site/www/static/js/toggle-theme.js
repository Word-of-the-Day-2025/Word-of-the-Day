// Keep track of cooldown state
var isCooldown = false;

// Function to update SVGs based on theme
function updateSVGs(theme) {
    var socialIcons = Array.from(document.querySelectorAll('img')).filter(function(img) {
        return img.src.endsWith('.svg');
    });
    for (var i = 0; i < socialIcons.length; i++) {
        var img = socialIcons[i];
        var parts = img.src.split('/');
        var baseName = parts[parts.length - 1];
        var staticBaseUrl = '/www/static/assets/';
        var newSrc = staticBaseUrl.replace(/\/?$/, '/') + 'svg/' + theme + '/' + baseName;
        img.src = newSrc;
    }
}

// Global function for theme toggling
function toggleTheme(event) {
    if (isCooldown) return;

    var root = document.documentElement;
    var currentTheme = root.getAttribute('data-theme');
    var newTheme = 'dark';
    
    if (event.shiftKey) {
        newTheme = 'hotdogstand';
    } else {
        newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    }

    root.setAttribute('data-theme', newTheme);
    try {
        localStorage.setItem('theme', newTheme);
    } catch (e) {}
    updateSVGs(newTheme);

    isCooldown = true;
    var toggleButton = document.querySelector('.theme-toggle');
    toggleButton.disabled = true;
    setTimeout(function() {
        isCooldown = false;
        toggleButton.disabled = false;
    }, 200);
}

// Initialize theme on page load
window.onload = function() {
    var root = document.documentElement;
    
    var savedTheme = null;
    try {
        savedTheme = localStorage.getItem('theme');
    } catch (e) {}

    if (savedTheme) {
        root.setAttribute('data-theme', savedTheme);
        updateSVGs(savedTheme);
    } else {
        var prefersLight = false;
        if (window.matchMedia) {
            try {
                prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;
            } catch (e) {}
        }
        var initialTheme = prefersLight ? 'light' : 'dark';
        root.setAttribute('data-theme', initialTheme);
        try {
            localStorage.setItem('theme', initialTheme);
        } catch (e) {}
        updateSVGs(initialTheme);
    }
};
