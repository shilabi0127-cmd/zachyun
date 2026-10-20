const $ = id => document.getElementById(id);
const names = {fcfs:'先到先接纳',nominal_milp:'名义时段整数规划',buffered_milp:'风险缓冲整数规划'};
let rows=[], result=null, reportText='';
const pct = x => x == null ? '不适用' : (x*100).toFixed(1)+'%';
const time = m => `${String(Math.floor(m/60)).padStart(2,'0')}:${String(Math.floor(m%60)).padStart(2,'0')}`;
async function api(path, body) {
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
  return data;
}
function message(text,error=false){$('message').textContent=text;$('message').style.color=error?'#a83e35':'#087f8c';}
function setRows(data){rows=data.reservations;$('data-count').textContent=`${rows.length} 条预约已载入`;$('preview').replaceChildren();for(const r of rows.slice(0,6)){const tr=document.createElement('tr');for(const v of [r.id,time(r.start),time(r.end),r.priority]){const td=document.createElement('td');td.textContent=v;tr.append(td);}$('preview').append(tr);}if(result){result=null;$('results').hidden=true;$('empty').hidden=false;$('run-meta').textContent='输入已改变，请重新运行';}message('数据有效，可以运行实验');}
$('sample').onclick=async()=>{try{setRows(await api(`/api/sample?seed=${Number($('seed').value)}`));}catch(e){message(e.message,true);}};
$('csv').onchange=async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>1000000)throw new Error('CSV 最大为 1 MB');setRows(await api('/api/import',{csv_text:await file.text()}));}catch(e){message(e.message,true);}event.target.value='';};
function metric(label,value){const line=document.createElement('div');line.className='metric';const a=document.createElement('span'),b=document.createElement('b');a.textContent=label;b.textContent=value;line.append(a,b);return line;}
function render(){
  $('empty').hidden=true;$('results').hidden=false;$('cards').replaceChildren();$('bars').replaceChildren();
  $('run-meta').textContent=`${result.config.trials} 轮 · ${(result.total_runtime_ms/1000).toFixed(2)} 秒 · ${result.scenario_hash.slice(0,8)}`;
  for(const [key,r] of Object.entries(result.policies)){
    const card=document.createElement('section');card.className='card'+(key==='buffered_milp'?' focus':'');
    const title=document.createElement('h3');title.textContent=names[key];card.append(title);
    const big=document.createElement('div');big.className='big';big.append(document.createTextNode(String(r.accepted)));const small=document.createElement('small');small.textContent=` / ${r.total} 条`;big.append(small);card.append(big);
    const caption=document.createElement('div');caption.className='caption';caption.textContent='接纳预约';card.append(caption);
    card.append(metric('接纳权重',r.accepted_weight.toFixed(1)),metric('预约收入',r.revenue.toFixed(2)),metric('优先用户接纳',pct(r.priority_acceptance_rate)),metric('冲突涉及率',pct(r.conflict_rate)));
    const bound=document.createElement('div');bound.className='bound';bound.textContent=`95% 抽样界 ${r.mc_95_bound?r.mc_95_bound.map(pct).join(' 至 '):'不适用'} · ${r.optimal?'已求得最优解':r.solver_status==='heuristic'?'顺序基准':'可行解 / 未证最优'}`;card.append(bound);$('cards').append(card);
    const bar=document.createElement('div');bar.className='bar-row';const label=document.createElement('span');label.textContent=names[key];const track=document.createElement('div');track.className='track';const fill=document.createElement('div');fill.className='fill';fill.style.width=pct(r.acceptance_rate);const val=document.createElement('span');val.className='bar-value';val.textContent=pct(r.acceptance_rate);track.append(fill,val);const risk=document.createElement('b');risk.textContent=pct(r.conflict_rate);bar.append(label,track,risk);$('bars').append(bar);
  }
  drawSchedule();
}
function svg(tag,attrs,text){const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,String(v));if(text!==undefined)el.textContent=text;return el;}
function drawSchedule(){if(!result)return;const data=result.policies[$('policy').value].schedule.filter(r=>r.accepted),slots=result.config.slots;
  const chart=$('gantt');chart.replaceChildren();const w=800,h=slots*43+55,left=58,right=16;
  chart.setAttribute('viewBox',`0 0 ${w} ${h}`);
  if(!data.length){chart.append(svg('text',{x:20,y:30,fill:'#62747c','font-size':13},'该策略没有接纳预约'));return;}
  const start=Math.floor(Math.min(...data.map(r=>r.protected_start))/60)*60,end=Math.ceil(Math.max(...data.map(r=>r.protected_end))/60)*60;
  const x=m=>left+(m-start)/(end-start)*(w-left-right);
  for(let t=start;t<=end;t+=60){chart.append(svg('line',{x1:x(t),x2:x(t),y1:25,y2:h-22,stroke:'#e5edef'}),svg('text',{x:x(t),y:15,'text-anchor':'middle',fill:'#62747c','font-size':10},time(t)));}
  for(let b=1;b<=slots;b++){const y=33+(b-1)*43;chart.append(svg('text',{x:0,y:y+16,fill:'#62747c','font-size':11},`泊位 ${b}`));}
  for(const r of data){const y=33+(r.bay-1)*43,color=r.priority>=3?'#0b8c85':'#5b8fa9';chart.append(svg('rect',{x:x(r.protected_start),y,width:x(r.protected_end)-x(r.protected_start),height:28,rx:3,fill:color,opacity:.18}));const rect=svg('rect',{x:x(r.start),y:y+3,width:x(r.end)-x(r.start),height:22,rx:3,fill:color});rect.append(svg('title',{},`${r.id} · ${time(r.start)} 至 ${time(r.end)} · 权重 ${r.priority}`));chart.append(rect);if(x(r.end)-x(r.start)>27)chart.append(svg('text',{x:x(r.start)+4,y:y+18,fill:'#fff','font-size':8,'pointer-events':'none'},r.id));}
}
$('policy').onchange=drawSchedule;
$('run').onclick=async()=>{if(!rows.length){message('请先导入预约',true);return;}const button=$('run');button.disabled=true;button.textContent='正在求解与仿真…';message('正在比较三种策略，首次求解可能稍慢');try{result=await api('/api/solve',{reservations:rows,config:{slots:Number($('slots').value),risk_budget:Number($('risk').value),trials:Number($('trials').value),seed:Number($('seed').value),objective:$('objective').value}});render();reportText=(await api('/api/report',{run_id:result.run_id})).report;$('report').textContent=reportText;message('实验完成，结果已保存于当前本地会话');}catch(e){message(e.message,true);}finally{button.disabled=false;button.textContent='运行三策略实验 ↗';}};
function download(name,text,type){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('json').onclick=()=>result&&download('parking-experiment.json',JSON.stringify(result,null,2),'application/json');
$('markdown').onclick=()=>result&&download('parking-report.md',reportText,'text/markdown;charset=utf-8');
$('schedule').onclick=()=>{if(!result)return;const cols=['id','start','end','priority','accepted','bay','protected_start','protected_end'];const csv=[cols.join(','),...result.policies[$('policy').value].schedule.map(r=>cols.map(k=>r[k]??'').join(','))].join('\r\n');download('parking-schedule.csv','\ufeff'+csv,'text/csv;charset=utf-8');};
$('explain').onclick=async()=>{if(!result)return;const button=$('explain');button.disabled=true;button.textContent='本地模型正在解读…';try{const data=await api('/api/report',{run_id:result.run_id,use_ollama:true,model:$('models').value});$('report').textContent=data.interpretation+'\n\n'+data.report;}catch(e){$('report').textContent=e.message+'\n\n'+reportText;}finally{button.disabled=false;button.textContent='本地模型解读';}};
async function init(){try{setRows(await api('/api/sample'));}catch(e){message(e.message,true);}try{const data=await api('/api/models');$('explain').disabled=!data.available||!data.models.length;$('model-status').textContent=data.available?`本地 Ollama · ${data.models.length} 个模型`:'Ollama 未启动 · 标准报告可用';if(data.models.length){$('models').replaceChildren();for(const model of data.models){const o=document.createElement('option');o.value=model;o.textContent=model;$('models').append(o);}}}catch(e){$('model-status').textContent='本地模型检测失败';$('explain').disabled=true;}}
init();
