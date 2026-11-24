import os,json,time,threading,datetime
from collections import deque
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler

TOKEN=os.environ.get("CLEF27_TOKEN","")
PORT=int(os.environ.get("PORT","10000"))
BOOKS=deque(maxlen=2400)
LOCK=threading.Lock()
PAGE=r"""<!DOCTYPE html><html lang="ro"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CL CLEF27 Mobile</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#03111e;color:#d7ebf8;font:14px Arial,sans-serif}header{padding:12px 14px;border-bottom:1px solid #23405b;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}h1{font-size:19px;margin:0}b.price{color:#38e2c8;font-size:25px}small{color:#80a5c2}.pill{background:#082942;border:1px solid #28506d;padding:6px 10px;border-radius:15px}main{max-width:1100px;margin:auto;padding:10px}.metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.tile,.panel{background:#071c31;border:1px solid #20415d;border-radius:10px;padding:12px}.tile strong{display:block;font-size:24px;margin-top:7px}.bid{color:#18dbc8}.ask{color:#ff5983}.panel{margin-top:9px}h2{margin:0 0 10px;font-size:15px}.buttons{display:flex;gap:8px;margin-bottom:8px}button{background:#082940;border:1px solid #2b5973;color:#d7ebf8;border-radius:7px;padding:8px 15px;cursor:pointer}.selected{background:#076658}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:right}.stats :first-child{text-align:left}.stats div{padding:7px 0;border-bottom:1px solid #183a53}.flag{text-align:center;font-weight:bold;padding:9px;color:#f8c47e}.grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(170px,250px);gap:9px;align-items:stretch}canvas{width:100%;height:390px;display:block}.footer{padding:8px;font-size:11px;color:#8ab0cd;text-align:center}@media(max-width:600px){.grid{grid-template-columns:1fr}.metrics strong{font-size:20px}canvas{height:290px}header h1{font-size:16px}}#login{position:fixed;inset:0;background:#03111e;display:grid;place-items:center;z-index:10}#login .panel{max-width:360px;width:90vw}input{padding:12px;width:100%;border:1px solid #42637b;background:#061c2f;color:white;border-radius:7px;margin:12px 0}#login button{width:100%;background:#086a5f}
</style></head><body>
<div id="login"><div class="panel"><h2>CL / CLEF27 — acces privat</h2><small>Introdu cheia de acces configurată pentru dashboardul mobil.</small><input id="key" type="password" placeholder="Cheie de acces"><button onclick="enter()">Deschide</button><p id="err" class="ask"></p></div></div>
<header><h1>CL / CLEF27 <span class="pill">LIVE</span></h1><div><b class="price" id="last">—</b> <small>USD/baril · Level 2</small></div><span class="pill" id="status">Aștept date</span></header>
<main><div class="metrics"><div class="tile">BID – cumpărare<strong class="bid" id="bid">—</strong><small>contracte</small></div><div class="tile">ASK – vânzare<strong class="ask" id="ask">—</strong><small>contracte</small></div></div>
<div class="panel"><h2>PULLING / STACKING <small> ±0,50 USD de Last</small></h2><div class="buttons"><button id="s5" onclick="period(5)">5 s</button><button id="s30" onclick="period(30)">30 s</button><button id="s60" onclick="period(60)" class="selected">60 s</button></div><div class="stats"><div>Parte</div><div>Stacking +</div><div>Scădere −</div><div class="bid">BID</div><div id="bs">—</div><div id="bp">—</div><div class="ask">ASK</div><div id="as">—</div><div id="ap">—</div></div><div class="flag" id="pressure">Date insuficiente</div><small>Variații observate ale ordinelor limită; nu identifică anulările separat de execuții.</small></div>
<div class="panel"><h2>POSIBILĂ ABSORBȚIE <small>30 s · indicativ</small></h2><div id="absorb">Fără zonă clară — necesită date istorice și Time & Sales pentru confirmare.</div></div>
<div class="grid"><div class="panel"><h2>HEATMAP · ultimele snapshoturi</h2><canvas id="heat"></canvas></div><div class="panel"><h2>DOM · Profil BID / ASK</h2><canvas id="profile"></canvas></div></div><div class="footer" id="stamp">Datele se transmit de la Quantower de pe PC. Fără date demo.</div></main>
<script>
var token=sessionStorage.getItem('clef27key')||'',s=60,book=null;
function el(x){return document.getElementById(x)}
function enter(){token=el('key').value.trim();sessionStorage.setItem('clef27key',token);load()}
function period(v){s=v;[5,30,60].forEach(function(x){el('s'+x).className=x===v?'selected':''});if(book)paint(book)}
async function load(){try{var r=await fetch('/api/state',{headers:{'X-Access-Token':token},cache:'no-store'});if(r.status===401){el('login').style.display='grid';el('err').innerText='Cheie incorectă';return}if(!r.ok)throw Error('HTTP '+r.status);book=await r.json();el('login').style.display='none';paint(book)}catch(e){el('status').textContent='Fără conexiune';}}
function fmt(x){return x===null||x===undefined?'—':Math.round(x).toLocaleString('ro-RO')}
function paint(d){
el('status').textContent=d.ageSec===null?'Aștept date':d.ageSec<30?'● LIVE':'Date istorice';
el('last').textContent=d.last===null?'—':Number(d.last).toFixed(2);
el('bid').textContent=fmt(d.totals.bid);el('ask').textContent=fmt(d.totals.ask);
var p=d.windows[String(s)];if(p){el('bs').textContent=fmt(p.bid.stacking);el('bp').textContent=fmt(p.bid.pulling);el('as').textContent=fmt(p.ask.stacking);el('ap').textContent=fmt(p.ask.pulling);var n=p.bid.net-p.ask.net;el('pressure').textContent=(n>0?'Presiune BID +':n<0?'Presiune ASK +':'Neutru ')+fmt(Math.abs(n))+' contracte';el('pressure').style.color=n>0?'#18dbc8':'#ff5983'}else{['bs','bp','as','ap'].forEach(function(k){el(k).textContent='—'});el('pressure').textContent='Date insuficiente'}
el('absorb').textContent=d.absorption||'BID – fără zonă clară · ASK – fără zonă clară';
el('stamp').textContent=d.time?'Ultimul snapshot: '+new Date(d.time*1000).toLocaleString('ro-RO')+' · Actualizare la 5 secunde':'Aștept date reale de la recorder';
drawHeat(d.history||[]);drawProfile(d.bids||[],d.asks||[],d.last)
}
function canvas(id){var c=el(id),w=c.clientWidth||320,h=c.clientHeight||280;var ratio=window.devicePixelRatio||1;c.width=w*ratio;c.height=h*ratio;var x=c.getContext('2d');x.scale(ratio,ratio);x.clearRect(0,0,w,h);return [x,w,h]}
function drawHeat(a){var v=canvas('heat'),x=v[0],w=v[1],h=v[2];if(!a.length)return;var prices=[];a.forEach(function(f){prices.push(...f.bids.map(function(r){return r[0]}),...f.asks.map(function(r){return r[0]}))});var last=a[a.length-1].last||80;var lo=last-2,hi=last+2;var bw=w/Math.max(1,a.length);var max=1;a.forEach(function(f){[f.bids,f.asks].forEach(function(side){side.forEach(function(r){if(r[0]>=lo&&r[0]<=hi)max=Math.max(max,r[1])})})});a.forEach(function(f,i){[f.bids,f.asks].forEach(function(side,si){side.forEach(function(r){if(r[0]<lo||r[0]>hi)return;var z=Math.min(1,Math.sqrt(r[1]/max));x.fillStyle=si?'rgba(252,74,129,'+(.12+.72*z)+')':'rgba(0,218,210,'+(.12+.72*z)+')';x.fillRect(i*bw,h-(r[0]-lo)/(hi-lo)*h,Math.ceil(bw)+1,2)})});if(f.last){x.fillStyle='#f5e7b4';x.fillRect(i*bw,h-(f.last-lo)/(hi-lo)*h,Math.max(1,bw),2)}});x.strokeStyle='#3de4cf';x.setLineDash([3,4]);x.beginPath();x.moveTo(0,h-(last-lo)/(hi-lo)*h);x.lineTo(w,h-(last-lo)/(hi-lo)*h);x.stroke()}
function drawProfile(bids,asks,last){var v=canvas('profile'),x=v[0],w=v[1],h=v[2];if(!last)return;var lo=last-2,hi=last+2,mid=w/2,max=1;[bids,asks].forEach(function(side){side.forEach(function(r){if(r[0]>lo&&r[0]<hi)max=Math.max(max,r[1])})});[bids,asks].forEach(function(side,si){x.fillStyle=si?'#ff5983':'#18dbc8';side.forEach(function(r){if(r[0]<lo||r[0]>hi)return;var y=h-(r[0]-lo)/(hi-lo)*h,b=(r[1]/max)*(w*.45);x.fillRect(si?mid:mid-b,y,b,2)})});x.strokeStyle='#476c82';x.beginPath();x.moveTo(mid,0);x.lineTo(mid,h);x.stroke()}
if(token)load();setInterval(function(){if(token)load()},5000);
</script></body></html>"""

def compute(frames):
    latest=frames[-1] if frames else None
    if not latest:return dict(last=None,ageSec=None,time=None,totals={'bid':0,'ask':0},windows={},bids=[],asks=[],history=[],absorption=None)
    last=latest.get('last')
    bids=latest['bids'];asks=latest['asks']
    windows={}
    for sec in [5,30,60]:
        old=next((f for f in reversed(frames) if f['ts']<=latest['ts']-sec),None)
        if not old or latest['ts']-old['ts']>sec+12:continue
        row={}
        for side in ('bid','ask'):
            cur={round(p,2):q for p,q in latest[side] if last is not None and abs(p-last)<=.5}
            past={round(p,2):q for p,q in old[side] if last is not None and abs(p-last)<=.5}
            diff=[cur.get(p,0)-past.get(p,0) for p in cur.keys()|past.keys()]
            row[side]={'stacking':round(sum(max(0,z) for z in diff)),'pulling':round(sum(max(0,-z) for z in diff)),'net':round(sum(diff))}
        windows[str(sec)]=row
    hist=list(frames)[-150:]
    step=max(1,len(hist)//90)
    return dict(last=last,ageSec=round(time.time()-latest['ts'],1),time=latest['ts'],totals={'bid':round(sum(r[1] for r in bids)),'ask':round(sum(r[1] for r in asks))},windows=windows,bids=bids,asks=asks,history=[{'ts':f['ts'],'last':f['last'],'bids':f['bids'],'asks':f['asks']} for f in hist[::step]],absorption='BID – fără zonă confirmată · ASK – fără zonă confirmată (fără Time & Sales)')
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def output(self,code,data,content='application/json'):
        raw=data if isinstance(data,bytes) else json.dumps(data).encode()
        self.send_response(code);self.send_header('Content-Type',content);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
    def auth(self):
        import hmac
        return bool(TOKEN) and hmac.compare_digest(self.headers.get('X-Access-Token',''),TOKEN)
    def do_GET(self):
        if self.path=='/health':return self.output(200,{'status':'ok'})
        if self.path=='/':return self.output(200,PAGE.encode('utf8'),'text/html; charset=utf-8')
        if self.path=='/api/state':
            if not self.auth():return self.output(401,{'error':'unauthorized'})
            with LOCK:data=compute(list(BOOKS))
            return self.output(200,data)
        return self.output(404,{'error':'not found'})
    def do_POST(self):
        if self.path!='/api/upload':return self.output(404,{'error':'not found'})
        if not self.auth():return self.output(401,{'error':'unauthorized'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<1 or size>2500000:return self.output(413,{'error':'size'})
            incoming=json.loads(self.rfile.read(size))
            if not isinstance(incoming,list) or len(incoming)>30:return self.output(400,{'error':'batch'})
            out=[]
            for r in incoming:
                if r.get('symbol')!='CLEF27':continue
                t=datetime.datetime.fromisoformat(r['utc'].replace('Z','+00:00')).timestamp()
                if abs(time.time()-t)>3600:continue
                bids=[[float(p),float(q)] for p,q in r['bids'] if float(q)>0][:600]
                asks=[[float(p),float(q)] for p,q in r['asks'] if float(q)>0][:600]
                if not bids or not asks:continue
                last=r.get('last')
                last=float(last) if last is not None else None
                if last is not None and not (0<last<1000):continue
                out.append({'ts':t,'bids':bids,'asks':asks,'last':last})
            with LOCK:
                for f in sorted(out,key=lambda o:o['ts']):
                    if not BOOKS or f['ts']>BOOKS[-1]['ts']:BOOKS.append(f)
            return self.output(200,{'ok':True,'accepted':len(out)})
        except (KeyError,ValueError,TypeError,OverflowError) as e:return self.output(400,{'error':'invalid data'})
if __name__=='__main__':
    if not TOKEN:raise SystemExit('Seteaza CLEF27_TOKEN in Environment!')
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
