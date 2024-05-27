#! /bin/bash

/app/tiggu/build.sh /app/site/project

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

# moving in app files after web files in order to overwrite

copy_dot_dirs /app/site/project/interim ./build/interim
copy_dot_dirs /app/site/project/public ./build/public
