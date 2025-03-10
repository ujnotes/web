#! /bin/bash

/app/tiggu/build.sh /app/site/project

cd /app

shopt -s extglob
copy_dot_dirs() {
  local source_dir=$1
  local dest_dir=$2
  
  shopt -s extglob

  cp -r $source_dir/* $dest_dir
  for dir in "$source_dir"/.!(.|git); do
    if [ -d "$dir" ] || [ -f "$dir" ]; then
      cp -r "$dir" "$dest_dir"
    fi
  done
}

# Create a temporary directory for backup
# TEMP_DIR=$(mktemp -d)

TEMP_DIR="./temp_$(date +%s)"
mkdir -p "$TEMP_DIR"

echo "Temporary directory created at: $TEMP_DIR"

# Create separate subdirectories in the temporary directory for public and interim
INTERIM_TEMP="$TEMP_DIR/interim"
PUBLIC_TEMP="$TEMP_DIR/public"
mkdir -p "$INTERIM_TEMP" "$PUBLIC_TEMP"

# Empty build/interim by moving its contents (except .git) to the interim subdirectory
echo "Moving files from project/build/interim (except .git) to $INTERIM_TEMP..."
find project/build/interim -mindepth 1 -maxdepth 1 ! -name ".git" -exec mv {} "$INTERIM_TEMP" \;

# Empty build/public by moving its contents to the public subdirectory
echo "Moving files from project/build/public to $PUBLIC_TEMP..."
find project/build/public -mindepth 1 -maxdepth 1 -exec mv {} "$PUBLIC_TEMP" \;

echo "Operation complete. The following files and directories have been moved:"
find "$TEMP_DIR" -mindepth 1 -maxdepth 2

copy_dot_dirs site/project/interim project/build/interim
copy_dot_dirs site/project/public project/build/public
