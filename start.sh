#!/bin/sh

# Navigate to the directory containing the script
cd "$(dirname "$0")"

# Run the main Python script
python3 src/main.py

# Wait for user input before closing (not standard in sh, but this mimics pause)
read -p 'Press enter to continue...'