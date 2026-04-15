#!/bin/bash
read -p "Commit message: " desc
git add . && \
git commit -m "$desc" && \
git push





# chmod +x git-push.sh
# nano .bashrc 
# alias push=~/path/to/git-push.sh
# ctrl + s (save)
# ctrl + x (exit)


# git remote add origin [copied web address]
# git push -u origin main