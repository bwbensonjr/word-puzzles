all: word-list-5.txt

word-list-5.txt:
	cat /usr/share/dict/words | grep -o -w "\w\{5\}" | tr '[:upper:]' '[:lower:]' > word-list-5.txt

