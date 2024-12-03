#Append a newline to every csv file in this folder
for FILE in *.csv; do echo "" >> $FILE ;done