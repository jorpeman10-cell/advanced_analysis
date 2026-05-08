import pymysql,json
from datetime import datetime as dt
c={'host':'127.0.0.1','port':3306,'user':'readonly','password':'Tstar2026!','database':'gllue','charset':'utf8mb4','cursorclass':pymysql.cursors.DictCursor}
with pymysql.connect(**c).cursor() as cur:
 cur.execute('SHOW TABLES')
 t=[r[f'Tables_in_{c["database"]}'] for r in cur.fetchall()]
print('Tables:',t)
r={}
for x in ['offersign','invoice','invoiceassignment','joborder','jobsubmission','user','team','client']:
 m=[a for a in t if a.lower()==x]
 if m:
  n=m[0]
  with pymysql.connect(**c).cursor() as cur:
   cur.execute(f'DESCRIBE `{n}`')
   r[n]={'cols':[{'f':a['Field'],'t':a['Type']} for a in cur.fetchall()]}
with open('report.json','w')as f:json.dump(r,f,ensure_ascii=False,indent=2)
print('done')
