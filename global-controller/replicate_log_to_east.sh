#!/bin/bash

# Original and temporary file names
ORIGINAL_FILE="trace_string.csv"
MODIFIED_FILE="temp.csv"
MERGED_FILE="merged.csv"

# Copy and replace text
if [ -f "$ORIGINAL_FILE" ]; then
    # Copy the original file and replace 'west' with 'east'
    sed 's/west/east/g' "$ORIGINAL_FILE" > "$MODIFIED_FILE"
    echo "Created modified file with replacements."

    # Merge the original and modified files
    cat "$ORIGINAL_FILE" "$MODIFIED_FILE" > "$MERGED_FILE"
    mv ${MERGED_FILE} ${ORIGINAL_FILE}
    rm ${MODIFIED_FILE}
    echo "Merged the original and modified files into $MERGED_FILE"
else
    echo "Error: $ORIGINAL_FILE does not exist."
fi
