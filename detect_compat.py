import pymysql,json
from datetime import datetime as dt
c={'host':'127.0.0.1','port':3306,'user':'readonly','password':'Tstar2026!','database':'gllue','charset':'utf8mb4','cursorclass':pymysql.cursors.DictCursor}
def q(sql):
 conn=pymysql.connect(**c)
 cur=conn.cursor()
 cur.execute(sql)
 rows=cur.fetchall()
 cur.close()
 conn.close()
 return rows
t=[r['Tables_in_'+c['database']] for r in q('SHOW TABLES')]
print('Tables: '+str(t))
r={}
for x in ['offersign','invoice','invoiceassignment','joborder','jobsubmission','user','team','client']:
 m=[a for a in t if a.lower()==x]
 if m:
  n=m[0]
  r[n]={'cols':[{'f':a['Field'],'t':a['Type']} for a in q('DESCRIBE `%s`' % n)]}
with open('report.json','w')as f:json.dump(r,f,ensure_ascii=False,indent=2)
print('done')
