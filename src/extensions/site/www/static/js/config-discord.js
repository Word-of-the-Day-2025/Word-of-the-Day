// Get URL parameters
const urlParams = new URLSearchParams(window.location.search);
const userId = urlParams.get('user_id');
const guildId = urlParams.get('guild_id');
const channelId = urlParams.get('channel_id');
const token = urlParams.get('token');

// Get form elements
const form = document.querySelector('form');
const timezoneSelect = document.getElementById('timezone-select');
const timeSingle = document.getElementById('time-single');
const includeDate = document.querySelector('input[name="include-date"]');
const includeIpa = document.querySelector('input[name="include-ipa"]');
const isDmy = document.querySelector('input[name="is-dmy"]');
const silentMode = document.querySelector('input[name="silent-mode"]');
const dateFormatRadios = document.querySelectorAll('input[name="date-format"]');
const resetButton = document.querySelector('button[type="reset"]');
const forgetButton = document.querySelector('button[type="forget"]');

// Default settings
const defaultSettings = {
    timezone: 'UTC',
    time: '00:00',
    includeDate: true,
    includeIpa: true,
    isDmy: true,
    silentMode: false,
    dateFormat: 'Medium'
};

// Handle form submission
form.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Get selected date format
    let selectedDateFormat = 'Medium';
    dateFormatRadios.forEach(radio => {
        if (radio.checked) {
            selectedDateFormat = radio.value;
        }
    });

    // Convert time to minutes since midnight
    const timeValue = timeSingle.value;
    const [hours, minutes] = timeValue.split(':').map(Number);
    const timeInMinutes = (hours * 60) + minutes;
    const dateFormat = selectedDateFormat

    // Prepare settings data
    const settings = {
        user_id: userId,
        guild_id: guildId,
        channel_id: channelId,
        token: token,
        time_settings: {
            timezone: timezoneSelect.value,
            time: timeInMinutes
        },
        message_format: {
            include_date: includeDate.checked,
            include_ipa: includeIpa.checked,
            display_dmy: isDmy.checked,
            silent_message: silentMode.checked
        },
        message_date_style: dateFormat
    };

    try {
        const response = await fetch('/api/discord_save_settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            alert('Settings saved successfully!');
        } else {
            alert('Failed to save settings: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        alert('An error occurred while saving settings.');
    }
});

// Handle reset button
resetButton.addEventListener('click', (e) => {
    e.preventDefault();

    // Reset to default values
    timezoneSelect.value = 'UTC';
    timeSingle.value = '00:00';
    includeDate.checked = true;
    includeIpa.checked = true;
    isDmy.checked = true;
    silentMode.checked = false;

    // Reset date format radio buttons
    dateFormatRadios.forEach(radio => {
        radio.checked = radio.value === 'Medium';
    });

    try {
        const response = fetch('/api/discord_reset_settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: userId,
                guild_id: guildId,
                channel_id: channelId,
                token: token
            })
        });
        response.then(async res => {
            const result = await res.json();
            if (res.ok && result.status === 'success') {
                alert('Settings have been reset to default values.');
            } else {
                alert('Failed to reset settings: ' + (result.error || 'Unknown error'));
            }
        });
    } catch (error) {
        console.error('Error resetting settings:', error);
        alert('An error occurred while resetting settings.');
    }
});

// Handle forget/unsubscribe button
forgetButton.addEventListener('click', async (e) => {
    e.preventDefault();

    const confirmMessage = 'Are you sure you want to unsubscribe and delete all your data? This action cannot be undone.';
    
    if (!confirm(confirmMessage)) {
        return;
    }

    const forgetData = {
        user_id: userId,
        guild_id: guildId,
        channel_id: channelId,
        token: token
    };

    try {
        const response = await fetch('/api/discord_forget', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(forgetData)
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            alert('Your data has been deleted. You will no longer receive Word of the Day messages.');
            // Redirect to home page after a short delay
            setTimeout(() => {
                window.location.href = '/';
            }, 2000);
        } else {
            alert('Failed to delete data: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error deleting data:', error);
        alert('An error occurred while deleting your data.');
    }
});