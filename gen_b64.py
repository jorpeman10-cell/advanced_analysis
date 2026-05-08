import base64

code = """import pymysql,json
from datetime import datetime as dt
c={'host':'127.0.0.1','port':3306,'user':'readonly','password':'Tstar2026!','database':'gllue','charset':'utf8mb4','cursorclass':pymysql.cursors.DictCursor}
k=['offersign','onboard','invoice','invoiceassignment','joborder','jobsubmission','candidate','user','team','client','clientinterview','cvsent','careertalk','function','industry','companylocation','contract']
def q(sql):
 with pymysql.connect(**c).cursor() as cur:
  cur.execute(sql)
  return cur.fetchall()
t=[r[f'Tables_in_{c["database"]}'] for r in q('SHOW TABLES')]
r={'database':c['database'],'total_tables':len(t),'all_tables':t,'key_tables':{}}
for x in k:
 m=[a for a in t if a.lower()==x]
 if m:
  n=m[0]
  s=[{'f':a['Field'],'t':a['Type']} for a in q(f'DESCRIBE `{n}`')]
  try:
   d=q(f'SELECT * FROM `{n}` LIMIT 3')
   for row in d:
    for k1,v in row.items():
     if isinstance(v,dt):row[k1]=v.strftime('%Y-%m-%d %H:%M:%S')
  except:d=[{'error':'err'}]
  r['key_tables'][n]={'count':q(f'SELECT COUNT(*) as cnt FROM `{n}`')[0]['cnt'],'structure':s,'sample':d}
with open('report.json','w')as f:json.dump(r,f,ensure_ascii=False,indent=2)
print('done: report.json')
"""

encoded = base64.b64encode(code.encode('utf-8')).decode('ascii')
print(encoded)
