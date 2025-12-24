# Discord Bot Setup

## Adding the Bot
To add the WOTD Discord bot to your server, you must go [here](https://discord.com/oauth2/authorize?client_id=1322109562119000149&permissions=0&integration_type=0&scope=bot). This link will open Discord and prompt you to choose the server you wish to add the bot to. The WOTD Discord bot can also be used in DMs.

## Permissions
The WOTD Discord bot does not come with any permissions by default, so it inherits the permissions of `@everyone`. If you want to make a channel that users can't send messages in, but where you want the WOTD to be posted, you must add the role automatically assigned to the bot or the bot user itself to the permissions list, and give it permission to send messages.

## Commands
Here is a complete list of all of the available commands which can be used with the WOTD Discord bot:

- `/subscribe`: Subscribes the current channel/DM to receive the WOTD
- `/unsubscribe`: Unsubscribes the current channel/DM from receiving the WOTD
- `/config`: Creates a private link for you to configure subscription settings
- `/config_reset`: Resets the subscription's configuration to use default settings
- `/forget_me`: Removes all data stored about you; this is functionally the same as the unsubscribe command
- `/request_data`: Sends a zip file of all data saved about you as part of your subscription

## Your Data
Your data can be requested and deleted at any time via commands. If you delete a channel or remove access from allowing the WOTD Discord bot to access it, the data for the subscription will be deleted the next time it attempts to send the Word of the Day, and you will have to resubscribe if you want to receive the Word of the Day again. To learn more about how we handle your data, you can read our privacy policy [here](/articles/privacy).