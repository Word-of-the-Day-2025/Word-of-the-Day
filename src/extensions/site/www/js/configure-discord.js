function saveSettings() {
    const form = document.getElementById('settings-form');
    const formData = new FormData(form);
    
    // Get basic form data
    const userId = formData.get('user_id');
    const guildId = formData.get('guild_id');
    const channelId = formData.get('channel_id');
    const token = formData.get('token');
    const timezone = formData.get('timezone');
    const messageDateStyle = formData.get('message_date_style');
    
    // Check if individual times are enabled
    const individualTimesEnabled = formData.get('individual_times') === 'true';
    
    // Get time data based on mode
    let timeData;
    if (individualTimesEnabled) {
        // Use individual day times
        timeData = {
            'Monday': formData.get('monday_time'),
            'Tuesday': formData.get('tuesday_time'),
            'Wednesday': formData.get('wednesday_time'),
            'Thursday': formData.get('thursday_time'),
            'Friday': formData.get('friday_time'),
            'Saturday': formData.get('saturday_time'),
            'Sunday': formData.get('sunday_time')
        };
    } else {
        // Use single time for all days
        const singleTime = formData.get('single_time');
        timeData = {
            'Monday': singleTime,
            'Tuesday': singleTime,
            'Wednesday': singleTime,
            'Thursday': singleTime,
            'Friday': singleTime,
            'Saturday': singleTime,
            'Sunday': singleTime
        };
    }
    
    // Get checkbox values (they will be 'on' if checked, null if unchecked)
    const wotdForUtc = formData.get('wotd_for_utc') === 'true';
    const includeDate = formData.get('include_date') === 'true';
    const includeIpa = formData.get('include_ipa') === 'true';
    const displayDmy = formData.get('display_dmy') === 'true';
    const sendUpdates = formData.get('send_updates') === 'true';
    
    // Debug: Log what we're actually getting from the form
    console.log('Form data being sent:');
    for (let [key, value] of formData.entries()) {
        console.log(key + ': ' + value);
    }
    
    console.log('Processed data:', {
        userId, guildId, channelId, token, timezone,
        timeData, wotdForUtc, includeDate, includeIpa, displayDmy, sendUpdates, messageDateStyle
    });
    
    fetch('/api/discord_save_settings', {
        method: 'POST',
        body: JSON.stringify({
            'user_id': userId,
            'guild_id': guildId,
            'channel_id': channelId,
            'token': token,
            'time_settings': {
                'timezone': timezone,
                'times': timeData,
                'wotd_for_utc': wotdForUtc
            },
            'message_format': {
                'include_date': includeDate,
                'include_ipa': includeIpa,
                'display_dmy': displayDmy,
                'send_updates': sendUpdates,
            },
            'message_date_style': messageDateStyle
        }),
        headers: {
            'Content-Type': 'application/json'
        }
    }).then(response => {
        if (response.ok) {
            alert('Settings saved successfully!');
        } else {
            response.text().then(text => {
                console.log('Error response:', text);
                alert('Failed to save settings. Please try again.');
            });
        }
    }).catch(error => {
        console.error('Fetch error:', error);
        alert('Failed to save settings. Please try again.');
    });
}

function resetSettings() {
    const form = document.getElementById('settings-form');
    const formData = new FormData(form);
    const userId = formData.get('user_id');
    const guildId = formData.get('guild_id');
    const channelId = formData.get('channel_id');
    const token = formData.get('token');
    if (confirm('Are you sure? This will reset your settings to the default values.')) {
        fetch('/api/discord_reset_settings', {
            method: 'POST',
            body: JSON.stringify({
                user_id: userId,
                guild_id: guildId,
                channel_id: channelId,
                token: token
            }),
            headers: {
                'Content-Type': 'application/json'
            }
        }).then(response => {
            if (response.ok) {
                alert('Settings have been reset to default.');
                location.reload();
            } else {
                alert('Failed to reset settings. Please try again.');
            }
        });
    }
}

function forgetMe() {
    const form = document.getElementById('settings-form');
    const formData = new FormData(form);
    const userId = formData.get('user_id');
    const guildId = formData.get('guild_id');
    const channelId = formData.get('channel_id');
    const token = formData.get('token');
    if (confirm('Are you sure? This will remove your subscription from our database, and you will need to reconfigure everything if you wish to use the service again.')) {
        fetch('/api/discord_forget_me', {
            method: 'POST',
            body: JSON.stringify({
                user_id: userId,
                guild_id: guildId,
                channel_id: channelId,
                token: token
            }),
            headers: {
                'Content-Type': 'application/json'
            }
        }).then(response => {
            if (response.ok) {
                alert('All settings have been forgotten.');
                location.reload();
            } else {
                alert('Failed to forget settings. Please try again.');
            }
        });
    }
}

function toggleDayTimes(checkbox) {
    const allDaysDiv = document.getElementById('all-days');
    const singleTimeDiv = document.getElementById('single-time');
    allDaysDiv.style.display = checkbox.checked ? 'flex' : 'none';
    singleTimeDiv.style.display = checkbox.checked ? 'none' : 'flex';
}

function updateAllTimes(selectedTime) {
    const timeSelects = document.querySelectorAll('#all-days select');
    timeSelects.forEach(select => {
        select.value = selectedTime;
    });
}