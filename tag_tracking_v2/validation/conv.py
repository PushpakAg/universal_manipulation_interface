import re,html
import os; S=os.path.dirname(os.path.abspath(__file__))+'/'
DARK='--bg:#12151c;--fg:#e6e9f0;--mut:#9aa3b8;--line:#2a3142;--card:#191e29;--ok:#6fd6a0;--okbg:#14301f;--bad:#ff9d92;--badbg:#3b1815;--warn:#f0c860;--warnbg:#3a2f0b;--info:#9db8f0;--infobg:#1c2845;--acc:#9db8f0;color-scheme:dark'
CSS='''<style>
:root{--bg:#fff;--fg:#1c2333;--mut:#5b6478;--line:#d9dde7;--card:#f6f7fb;--ok:#1a7f4b;--okbg:#e2f5ea;--bad:#b42318;--badbg:#fde7e4;--warn:#9a6700;--warnbg:#fff3cd;--info:#34508a;--infobg:#e6edfb;--acc:#34508a}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){@@D@@}}
:root[data-theme="dark"]{@@D@@}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 Inter,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1280px;margin:0 auto;padding-block:24px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1{font-size:26px;margin:0 0 4px;text-wrap:balance}h2{font-size:20px;margin:36px 0 8px;border-bottom:1px solid var(--line);padding-bottom:6px;text-wrap:balance}h3{font-size:16px;margin:20px 0 6px}
p,li{max-width:100ch}.mut{color:var(--mut)}code{font:12.5px ui-monospace,Menlo,monospace;background:var(--card);padding:1px 5px;border-radius:4px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:14px 0}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;min-width:0}.card .n{font-size:26px;font-weight:650}.card .l{color:var(--mut);font-size:13px}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:8px;max-width:100%}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;white-space:nowrap}th{background:var(--card)}td.w{white-space:normal;min-width:200px}tr:last-child td{border-bottom:0}
.b{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600}.ok{background:var(--okbg);color:var(--ok)}.bad{background:var(--badbg);color:var(--bad)}.warn{background:var(--warnbg);color:var(--warn)}.info{background:var(--infobg);color:var(--info)}
details{border:1px solid var(--line);border-radius:8px;margin:6px 0;background:var(--card)}summary{cursor:pointer;padding:8px 12px;font-weight:600}details .in{padding:0 12px 12px}
.callout{border:1px solid var(--line);background:var(--card);padding:10px 14px;border-radius:8px;margin:12px 0}.num{text-align:right;font-variant-numeric:tabular-nums}
a:focus-visible,summary:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
@media (max-width:600px){h1{font-size:21px}}
</style>'''.replace('@@D@@',DARK)
def wrap(title,body):
    return '<title>'+title+'</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'+CSS+'\n<main>\n'+body+'\n</main>\n'
h=open('mcap_comparison_s3_orig_v2.html').read()
body=h[h.index('<main>')+6:h.index('</main>')]
open(S+'comparison.html','w').write(wrap('MCAP Comparison Station 1',body))
md=open('DataPRD1019_mcap_delivery_checklist.md').read().split('\n')
def inl(t):
    t=html.escape(t,quote=False)
    t=re.sub(r'`([^`]+)`',r'<code>\1</code>',t); t=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',t); return t
BADGE={'PASS':'ok','FAIL':'bad','WARN':'warn','INFO':'info'}
def cell(c):
    return re.sub(r'\b(PASS|FAIL|WARN|INFO)\b',lambda m:'<span class="b %s">%s</span>'%(BADGE[m.group(1)],m.group(1)),inl(c.strip()))
out=[];i=0
while i<len(md):
    l=md[i]
    if l.startswith('# '): out.append('<h1>'+inl(l[2:])+'</h1>')
    elif l.startswith('## '): out.append('<h2>'+inl(l[3:])+'</h2>')
    elif l.startswith('### '): out.append('<h3>'+inl(l[4:])+'</h3>')
    elif l.startswith('|'):
        rows=[]
        while i<len(md) and md[i].startswith('|'): rows.append(md[i]); i+=1
        i-=1
        cells=[r.strip().strip('|').split(' | ') for r in rows if not re.match(r'^\|[-| ]+\|$',r)]
        wide=len(cells[0])>6
        t='<div class="tw"><table><tr>'+''.join('<th>'+inl(c)+'</th>' for c in cells[0])+'</tr>'
        for r in cells[1:]: t+='<tr>'+''.join(('<td>' if wide else '<td class="w">')+cell(c)+'</td>' for c in r)+'</tr>'
        out.append(t+'</table></div>')
    elif re.match(r'^\d+\. ',l):
        items=[]
        while i<len(md) and re.match(r'^\d+\. ',md[i]): items.append(re.sub(r'^\d+\. ','',md[i])); i+=1
        i-=1; out.append('<ol>'+''.join('<li>'+inl(x)+'</li>' for x in items)+'</ol>')
    elif l.strip(): out.append('<p>'+inl(l)+'</p>')
    i+=1
open(S+'checklist.html','w').write(wrap('Station 1 MCAP Delivery Checklist','\n'.join(out)))
print('ok')
