import sys, json
sys.path.append(r'C:\Users\EDY\recruiter_finance_tool\advanced_analysis')
from gllue_client import GllueConfig, GllueAPIClient

config = GllueConfig(base_url='http://118.190.96.172', username='steven.huang@tstarmc.com', password='123456')
client = GllueAPIClient(config)

resp = client._make_request('GET', '/rest/invoiceassignment/simple_list_with_ids', params={
    'fields': 'id,revenue,invoice__amount,invoice__status,invoice__joborder,invoice__joborder__jobTitle,invoice__offersign,invoice__offersign__signDate,user____name__',
    'paginate_by': 5,
    'page': 1
})
if 'result' in resp:
    items = resp['result'].get('invoiceassignment', [])
    invoices = resp['result'].get('invoice', [])
    joborders = resp['result'].get('joborder', [])
    offersigns = resp['result'].get('offersign', [])
    users = resp['result'].get('user', [])
    
    print('InvoiceAssignments:', len(items))
    print('Invoices:', len(invoices))
    print('JobOrders:', len(joborders))
    print('OfferSigns:', len(offersigns))
    print('Users:', len(users))
    
    for item in items[:3]:
        inv_id = item.get('invoice')
        inv = next((i for i in invoices if i['id'] == inv_id), None)
        jo_id = inv.get('joborder') if inv else None
        jo = next((j for j in joborders if j['id'] == jo_id), None)
        print('IA', item['id'], ': revenue=', item['revenue'], ', invoice=', inv_id, ', joborder=', jo_id)
        if jo:
            print('  JobOrder:', json.dumps(jo, ensure_ascii=False)[:200])
        print('---')
