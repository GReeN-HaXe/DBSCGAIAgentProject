import sqlite3
conn=sqlite3.connect("dbdatabase/dbs_masters.db")
cur=conn.cursor()
for cid in (52,5):
    row=cur.execute("select card_number, card_name, card_skill_unstyled, card_back_name, card_back_power, card_back_skill_unstyled from cards where id=?", (cid,)).fetchone()
    print("ID", cid)
    for i,v in enumerate(row):
        print(i, v)
    print("---")
conn.close()
