#!/usr/bin/env python3
import json
import base64
import urllib.request
import urllib.parse
from datetime import datetime
from collections import defaultdict
from pathlib import Path

CFG_PATH = Path('/data/.openclaw/workspace/secrets/xero_urgentcool.json')
OUT_HTML = Path('/data/.openclaw/workspace/xero-callback/revenue.html')
OUT_HTML_2 = Path('/data/.openclaw/workspace/xero-callback/revenue-anonymised.html')
OUT_JSON = Path('/data/.openclaw/workspace/xero-callback/revenue_data_mar26.json')
MONTHS = [(2025, m) for m in range(4, 13)] + [(2026, m) for m in range(1, 4)]
MONTH_LABELS = ['Apr 25', 'May 25', 'Jun 25', 'Jul 25', 'Aug 25', 'Sep 25', 'Oct 25', 'Nov 25', 'Dec 25', 'Jan 26', 'Feb 26', 'Mar 26']


def fmt_money(v, decimals=0):
    if abs(v) < 0.005:
        return '-'
    sign = '-' if v < 0 else ''
    v = abs(v)
    if decimals == 0:
        return f"{sign}${round(v):,.0f}"
    return f"{sign}${v:,.2f}"


def auth_token(cfg):
    auth = base64.b64encode(f"{cfg['client_id']}:{cfg['client_secret']}".encode()).decode()
    data = urllib.parse.urlencode({
        'grant_type': 'client_credentials',
        'scope': cfg['scopes']
    }).encode()
    req = urllib.request.Request(
        'https://identity.xero.com/connect/token',
        data=data,
        headers={
            'Authorization': f'Basic {auth}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())['access_token']


def api_get(token, tenant_id, path, params=None):
    url = 'https://api.xero.com/api.xro/2.0/' + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + token,
        'Xero-tenant-id': tenant_id,
        'Accept': 'application/json'
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def fetch_all(token, tenant_id, path, key, where):
    page = 1
    out = []
    while True:
        batch = api_get(token, tenant_id, path, {'where': where, 'page': page})[key]
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def parse_ym(s):
    d = datetime.fromisoformat(s.replace('Z', '+00:00'))
    return d.year, d.month


def include_line(contact_name, line_item):
    desc = (line_item.get('Description') or '').upper()
    code = str(line_item.get('AccountCode') or '')
    if contact_name == 'Fresh Direct - Palmerston North':
        if code == '469':
            return False
        if 'POWER ON CHARGE' in desc or 'POWER ON-CHARGE' in desc:
            return False
        if 'RENT' in desc:
            return False
    return True


def doc_amount(doc, filtered=True):
    name = doc['Contact']['Name']
    total = 0.0
    for li in doc.get('LineItems', []):
        if filtered and not include_line(name, li):
            continue
        total += float(li.get('LineAmount') or 0)
    return total


def build_flags(values):
    prev3 = values[6:9]   # Oct-Dec 2025
    last3 = values[9:12]  # Jan-Mar 2026
    flags = []
    prev_avg = sum(prev3) / 3
    last_avg = sum(last3) / 3
    if all(abs(v) < 0.005 for v in last3) and any(v > 0 for v in values[:9]):
        flags.append(('down', 'down 100%'))
        flags.append(('churned', 'churned'))
        flags.append(('down', '3/3 zero months'))
    elif prev_avg > 0:
        decline = (prev_avg - last_avg) / prev_avg
        if decline >= 0.30:
            flags.append(('down', f"down {round(decline * 100):.0f}%"))
    return flags


def render(summary):
    rows_html = []
    for idx, row in enumerate(summary['rows'], start=1):
        flags = build_flags(row['months'])
        flagged_class = 'flagged' if flags else ''
        name = row['name']
        if flags:
            for cls, label in flags:
                name += f' <span class="flag {cls}">{label}</span>'
        cells = []
        for v in row['months']:
            if abs(v) < 0.005:
                cells.append('<td style="color:#475569">-</td>')
            elif v < 0:
                cells.append(f'<td class="neg">{fmt_money(v)}</td>')
            else:
                cells.append(f'<td>{fmt_money(v)}</td>')
        total_cls = ' class="neg"' if row['total'] < 0 else ''
        rows_html.append(
            f'<tr data-total="{row["total"]}" class="{flagged_class}"><td>{idx}</td><td>{name}</td>'
            + ''.join(cells)
            + f'<td{total_cls}><strong>{fmt_money(row["total"])}</strong></td></tr>'
        )

    head_months = ''.join(f'<th>{m}</th>' for m in MONTH_LABELS)
    foot_months = ''.join(f'<td>{fmt_money(v)}</td>' for v in summary['month_totals'])

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Urgent Cool - Revenue by Client</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:20px}}
h1{{font-size:22px;margin-bottom:4px;color:#fff}}
.subtitle{{color:#94a3b8;margin-bottom:20px;font-size:14px}}
.controls{{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center}}
.controls input,.controls select{{background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:8px 12px;border-radius:6px;font-size:14px}}
.controls input::placeholder{{color:#64748b}}
.kpi-row{{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}}
.kpi{{background:#1e293b;border-radius:8px;padding:16px 20px;flex:1;min-width:150px}}
.kpi .label{{color:#94a3b8;font-size:12px;text-transform:uppercase;letter-spacing:0.5px}}
.kpi .value{{font-size:24px;font-weight:700;color:#fff;margin-top:4px}}
.kpi .value.green{{color:#34d399}}
.note{{background:#1e293b;border-left:3px solid #f59e0b;padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:16px;font-size:13px;color:#fbbf24}}
.table-wrap{{overflow-x:auto;border-radius:8px;border:1px solid #1e293b}}
table{{width:100%;border-collapse:collapse;font-size:13px;white-space:nowrap}}
thead th{{background:#1e293b;color:#94a3b8;padding:10px 12px;text-align:right;position:sticky;top:0;font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:0.5px}}
thead th:first-child,thead th:nth-child(2){{text-align:left}}
thead th:last-child{{color:#f59e0b}}
tbody td{{padding:8px 12px;text-align:right;border-bottom:1px solid #1e293b}}
tbody td:first-child{{text-align:center;width:30px}}
tbody td:nth-child(2){{text-align:left;color:#fff;font-weight:500;max-width:250px;overflow:hidden;text-overflow:ellipsis}}
tbody tr:hover{{background:#1e293b}}
tbody tr.hidden{{display:none}}
tfoot td{{padding:10px 12px;text-align:right;font-weight:700;background:#1e293b;color:#f59e0b;border-top:2px solid #334155}}
tfoot td:first-child,tfoot td:nth-child(2){{text-align:left}}
.neg{{color:#f87171}}
.flag{{display:inline-block;background:#7f1d1d;color:#fca5a5;padding:2px 6px;border-radius:4px;font-size:10px;margin-left:6px;font-weight:600}}
.flag.churned{{background:#7f1d1d}}
.flag.down{{background:#78350f;color:#fde68a}}
.export-btn{{background:#3b82f6;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600}}
.export-btn:hover{{background:#2563eb}}
.filter-btn{{background:#334155;color:#e2e8f0;border:none;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:12px}}
.filter-btn.active{{background:#dc2626;color:#fff}}
</style>
</head>
<body>
<h1>Urgent Cool Logistics — Revenue by Client</h1>
<p class="subtitle">April 2025 – March 2026 · {summary['clients']} clients · Source: Xero (invoices less credit notes, ex-GST)</p>
<div class="note">⚠️ Fresh Direct Palmerston North: Rent and power on-charges excluded — showing transport revenue only ({fmt_money(summary['fd_net'])} vs {fmt_money(summary['fd_gross'])} gross)</div>

<div class="kpi-row">
<div class="kpi"><div class="label">Transport Revenue</div><div class="value green">{fmt_money(summary['grand_total'])}</div></div>
<div class="kpi"><div class="label">Invoices</div><div class="value">{summary['invoice_count']:,}</div></div>
<div class="kpi"><div class="label">Credit Notes</div><div class="value">{summary['credit_count']:,}</div></div>
<div class="kpi"><div class="label">Avg Monthly Revenue</div><div class="value green">{fmt_money(summary['avg_monthly'])}</div></div>
<div class="kpi"><div class="label">Clients</div><div class="value">{summary['clients']}</div></div>
</div>

<div class="controls">
<input type="text" id="search" placeholder="🔍 Search client..." oninput="filterTable()">
<select id="minRev" onchange="filterTable()">
<option value="0" selected>All clients</option>
<option value="1000">Revenue &gt; $1,000</option>
<option value="5000">Revenue &gt; $5,000</option>
<option value="10000">Revenue &gt; $10,000</option>
<option value="50000">Revenue &gt; $50,000</option>
<option value="100000">Revenue &gt; $100,000</option>
</select>
<button class="filter-btn" id="flagBtn" onclick="toggleFlags()">🚩 Flagged Only</button>
<button class="export-btn" onclick="exportCSV()">📥 Export CSV</button>
</div>

<div class="table-wrap">
<table id="revTable">
<thead><tr>
<th>#</th>
<th>Client</th>
{head_months}
<th>TOTAL</th>
</tr></thead>
<tbody>
{''.join(rows_html)}
</tbody>
<tfoot><tr><td></td><td>TOTAL</td>{foot_months}<td>{fmt_money(summary['grand_total'])}</td></tr></tfoot>
</table></div>

<script>
let flagsOnly = false;

function filterTable() {{
  const q = document.getElementById('search').value.toLowerCase();
  const min = parseFloat(document.getElementById('minRev').value);
  const rows = document.querySelectorAll('#revTable tbody tr');
  rows.forEach(r => {{
    const name = r.children[1].textContent.toLowerCase();
    const total = parseFloat(r.dataset.total);
    let show = name.includes(q) && total >= min;
    if (flagsOnly && !r.classList.contains('flagged')) show = false;
    r.classList.toggle('hidden', !show);
  }});
}}

function toggleFlags() {{
  flagsOnly = !flagsOnly;
  document.getElementById('flagBtn').classList.toggle('active', flagsOnly);
  if (flagsOnly) document.getElementById('minRev').value = '0';
  filterTable();
}}

function exportCSV() {{
  const rows = document.querySelectorAll('#revTable thead tr, #revTable tbody tr:not(.hidden), #revTable tfoot tr');
  let csv = '';
  rows.forEach(r => {{
    const cells = [...r.querySelectorAll('th,td')].map(c => {{
      let t = c.textContent.replace(/[📉🚨⚠️]/g,'').trim();
      return '"' + t.replace(/"/g,'""') + '"';
    }});
    csv += cells.join(',') + '\n';
  }});
  const blob = new Blob([csv], {{type:'text/csv'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'urgent_cool_revenue_apr25_mar26.csv';
  a.click();
}}

filterTable();
</script>
</body></html>
'''


def main():
    cfg = json.loads(CFG_PATH.read_text())
    token = auth_token(cfg)
    where = 'Date>=DateTime(2025,4,1)&&Date<DateTime(2026,4,1)&&Contact.Name!=null'
    invoices = fetch_all(token, cfg['tenant_id'], 'Invoices', 'Invoices', 'Type=="ACCREC"&&' + where)
    credits = fetch_all(token, cfg['tenant_id'], 'CreditNotes', 'CreditNotes', 'Type=="ACCRECCREDIT"&&' + where)

    monthly = defaultdict(lambda: defaultdict(float))
    fd_net = 0.0
    fd_gross = 0.0

    for doc in invoices:
        ym = parse_ym(doc['DateString'])
        name = doc['Contact']['Name']
        amt = doc_amount(doc, filtered=True)
        monthly[name][ym] += amt
        if name == 'Fresh Direct - Palmerston North':
            fd_net += amt
            fd_gross += doc_amount(doc, filtered=False)

    for doc in credits:
        ym = parse_ym(doc['DateString'])
        name = doc['Contact']['Name']
        amt = doc_amount(doc, filtered=True)
        monthly[name][ym] -= amt
        if name == 'Fresh Direct - Palmerston North':
            fd_net -= amt
            fd_gross -= doc_amount(doc, filtered=False)

    rows = []
    for name, vals in monthly.items():
        months = [round(vals.get(m, 0.0), 2) for m in MONTHS]
        rows.append({
            'name': name,
            'months': months,
            'total': round(sum(months), 2)
        })

    rows.sort(key=lambda r: (r['total'], r['name']), reverse=True)

    summary = {
        'invoice_count': len(invoices),
        'credit_count': len(credits),
        'grand_total': round(sum(r['total'] for r in rows), 2),
        'avg_monthly': round(sum(r['total'] for r in rows) / 12, 2),
        'clients': len(rows),
        'fd_net': round(fd_net, 2),
        'fd_gross': round(fd_gross, 2),
        'month_totals': [round(sum(r['months'][i] for r in rows), 2) for i in range(12)],
        'rows': rows
    }

    OUT_JSON.write_text(json.dumps(summary, indent=2))
    html = render(summary)
    OUT_HTML.write_text(html)
    OUT_HTML_2.write_text(html)
    print(json.dumps({k: summary[k] for k in ['invoice_count', 'credit_count', 'grand_total', 'avg_monthly', 'clients']}, indent=2))


if __name__ == '__main__':
    main()
