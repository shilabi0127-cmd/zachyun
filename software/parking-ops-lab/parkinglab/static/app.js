const $ = id => document.getElementById(id);
const names = {fcfs:'先到先得',nominal_milp:'名义时段分配',fixed_buffer_milp:'固定缓冲分配',buffered_milp:'分位数缓冲分配',risk_milp:'逐用户风险约束分配'};
let rows=[], result=null, reportText='';
const pct = x => x == null ? '不适用' : (x*100).toFixed(1)+'%';
const time = m => `${m<0?'-':''}${String(Math.floor(Math.abs(m)/60)).padStart(2,'0')}:${String(Math.floor(Math.abs(m)%60)).padStart(2,'0')}`;
async function api(path, body) {
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
  return data;
}
function message(text,error=false){$('message').textContent=text;$('message').style.color=error?'#a83e35':'#087f8c';}
function setRows(data){rows=data.reservations;$('data-count').textContent=`${rows.length} 条预约已载入`;$('preview').replaceChildren();for(const r of rows.slice(0,6)){const tr=document.createElement('tr');for(const v of [r.id,time(r.start),time(r.end),r.priority]){const td=document.createElement('td');td.textContent=v;tr.append(td);}$('preview').append(tr);}if(result){result=null;$('results').hidden=true;$('empty').hidden=false;$('run-meta').textContent='输入已改变，请重新运行';}message('数据有效，可以运行实验');}
$('sample').onclick=async()=>{try{setRows(await api(`/api/sample?seed=${Number($('seed').value)}&count=${Number($('count').value)}`));}catch(e){message(e.message,true);}};
$('csv').onchange=async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>1000000)throw new Error('CSV 最大为 1 MB');setRows(await api('/api/import',{csv_text:await file.text()}));}catch(e){message(e.message,true);}event.target.value='';};
function metric(label,value){const line=document.createElement('div');line.className='metric';const a=document.createElement('span'),b=document.createElement('b');a.textContent=label;b.textContent=value;line.append(a,b);return line;}
function render(){
  $('empty').hidden=true;$('results').hidden=false;$('cards').replaceChildren();$('bars').replaceChildren();
  $('run-meta').textContent=`${result.config.trials} 轮 · ${(result.total_runtime_ms/1000).toFixed(2)} 秒 · ${result.scenario_hash.slice(0,8)}`;
  for(const [key,r] of Object.entries(result.policies)){
    const card=document.createElement('section');card.className='card'+(key==='risk_milp'?' focus':'');
    const title=document.createElement('h3');title.textContent=names[key];card.append(title);
    const big=document.createElement('div');big.className='big';big.append(document.createTextNode(String(r.accepted)));const small=document.createElement('small');small.textContent=` / ${r.total} 条`;big.append(small);card.append(big);
    const caption=document.createElement('div');caption.className='caption';caption.textContent='接纳预约';card.append(caption);
    card.append(metric('接纳权重',r.accepted_weight.toFixed(1)),metric('预约收入',r.revenue.toFixed(2)),metric('优先用户接纳',pct(r.priority_acceptance_rate)),metric('冲突涉及率',pct(r.conflict_rate)),metric('超出风险上限的订单',String(r.requests_over_risk_budget)),metric('计算耗时',r.solver_runtime_ms.toFixed(1)+' ms'),metric('求解间隙',r.mip_gap==null?'未返回':pct(r.mip_gap)));
    const bound=document.createElement('div');bound.className='bound';bound.textContent=`95% 抽样界 ${r.mc_95_bound?r.mc_95_bound.map(pct).join(' 至 '):'不适用'} · ${r.optimal?'已求得最优解':r.solver_status==='heuristic'?'顺序基准':r.solution_source==='verified_greedy_fallback'?'核对通过的贪心备选':'可行解 / 未证最优'}`;card.append(bound);$('cards').append(card);
    const bar=document.createElement('div');bar.className='bar-row';const label=document.createElement('span');label.textContent=names[key];const track=document.createElement('div');track.className='track';const fill=document.createElement('div');fill.className='fill';fill.style.width=pct(r.acceptance_rate);const val=document.createElement('span');val.className='bar-value';val.textContent=pct(r.acceptance_rate);track.append(fill,val);const risk=document.createElement('b');risk.textContent=pct(r.conflict_rate);bar.append(label,track,risk);$('bars').append(bar);
  }
  drawSchedule();renderDecisions();
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
$('policy').onchange=()=>{drawSchedule();renderDecisions();};
$('run').onclick=async()=>{if(!rows.length){message('请先导入预约',true);return;}const button=$('run');const controls=[...document.querySelectorAll('aside input,aside select,aside button')].map(el=>[el,el.disabled]);for(const [el] of controls)el.disabled=true;button.disabled=true;button.textContent='正在求解与仿真…';message('正在比较五种策略，风险分配可能用满设定的求解时限');try{result=await api('/api/solve',{reservations:rows,config:{slots:Number($('slots').value),risk_budget:Number($('risk').value),trials:Number($('trials').value),seed:Number($('seed').value),objective:$('objective').value,fixed_buffer_minutes:Number($('fixed-buffer').value),deviation_distribution:$('distribution').value,time_limit:Number($('time-limit').value)}});render();reportText=(await api('/api/report',{run_id:result.run_id})).report;$('report').textContent=reportText;message('实验完成，结果已保存于当前本地会话');}catch(e){message(e.message,true);}finally{for(const [el,disabled] of controls)el.disabled=disabled;button.disabled=false;button.textContent='计算分配与对比 ↗';}};
function download(name,text,type){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('json').onclick=()=>result&&download('parking-experiment.json',JSON.stringify(result,null,2),'application/json');
$('markdown').onclick=()=>result&&download('parking-report.md',reportText,'text/markdown;charset=utf-8');
$('schedule').onclick=()=>{if(!result)return;const cols=['id','start','end','fee','priority','accepted','bay','early_buffer_minutes','late_buffer_minutes','failure_tolerance','conflict_probability_upper_bound','observed_conflict_rate'];const csv=[cols.join(','),...result.policies[$('policy').value].schedule.map(r=>cols.map(k=>r[k]??'').join(','))].join('\r\n');download('parking-schedule.csv','\ufeff'+csv,'text/csv;charset=utf-8');};
$('explain').onclick=async()=>{if(!result)return;const button=$('explain');button.disabled=true;button.textContent='本地模型正在解读…';try{const data=await api('/api/report',{run_id:result.run_id,use_ollama:true,model:$('models').value});$('report').textContent=data.interpretation+'\n\n'+data.report;}catch(e){$('report').textContent=e.message+'\n\n'+reportText;}finally{button.disabled=false;button.textContent='本地模型解读';}};
async function init(){try{setRows(await api('/api/sample'));}catch(e){message(e.message,true);}try{const data=await api('/api/models');$('explain').disabled=!data.available||!data.models.length;$('model-status').textContent=data.available?`本地 Ollama · ${data.models.length} 个模型`:'Ollama 未启动 · 标准报告可用';if(data.models.length){$('models').replaceChildren();for(const model of data.models){const o=document.createElement('option');o.value=model;o.textContent=model;$('models').append(o);}}}catch(e){$('model-status').textContent='本地模型检测失败';$('explain').disabled=true;}}


function tableRow(target,values,warning=false){const tr=document.createElement('tr');if(warning)tr.className='warning-row';for(const value of values){const td=document.createElement('td');td.textContent=value;tr.append(td);}$(target).append(tr);}
function renderDecisions(){
  for(const id of ['orders','risk-pairs','buffers'])$(id).replaceChildren();
  const selected=result.policies[$('policy').value];
  for(const r of selected.schedule){tableRow('orders',[r.id,r.accepted?'接纳':'未接纳',r.bay??'无',r.early_buffer_minutes.toFixed(1)+' / '+r.late_buffer_minutes.toFixed(1),pct(r.failure_tolerance),pct(r.conflict_probability_upper_bound),pct(r.observed_conflict_rate)],r.accepted&&r.conflict_probability_upper_bound>r.failure_tolerance+1e-7);}
  for(const p of selected.risk_pairs.slice(0,20))tableRow('risk-pairs',[p.bay,p.first+' / '+p.second,pct(p.raw_overlap_probability),pct(p.overlap_probability_upper_bound)]);
  $('risk-note').textContent=`共 ${selected.same_bay_pair_count} 组同泊位组合，表内显示风险最高的 ${Math.min(20,selected.risk_pairs.length)} 组；导出最多 50 组。原始概率尚未计入异常时长修正，约束使用修正后的上界。`;
  for(const p of selected.buffer_recommendations)tableRow('buffers',[p.bay,p.previous+' → '+p.following,p.scheduled_gap_minutes.toFixed(1),p.suggested_directional_gap_minutes.toFixed(1),p.additional_gap_minutes.toFixed(1)],p.additional_gap_minutes>.01);
}
function exportRows(name,records){if(!records.length){message('当前策略没有对应记录');return;}const columns=Object.keys(records[0]);const escape=v=>'"'+String(v??'').replaceAll('"','""')+'"';download(name,'\ufeff'+[columns.map(escape).join(','),...records.map(r=>columns.map(k=>escape(r[k])).join(','))].join('\r\n'),'text/csv;charset=utf-8');}
$('risk-export').onclick=()=>result&&exportRows('risk-pairs.csv',result.policies[$('policy').value].risk_pairs);
$('buffer-export').onclick=()=>result&&exportRows('buffer-recommendations.csv',result.policies[$('policy').value].buffer_recommendations);
$('apply-deviations').onclick=()=>{
  const fields={'arrival_mean':'arrival-mean','arrival_std':'arrival-std','departure_mean':'departure-mean','departure_std':'departure-std'};
  const values={};for(const [key,id] of Object.entries(fields)){if(!$(id).reportValidity())return;values[key]=Number($(id).value);}
  setRows({reservations:rows.map(r=>({...r,...values}))});message('已更新全部订单的时间偏差，请重新计算');
};
let benchmark=null;
function renderBenchmark(){if(!benchmark)return;$('benchmark').replaceChildren();for(const r of benchmark.summary.filter(r=>r.distribution===$('benchmark-distribution').value))tableRow('benchmark',[r.size+' / '+r.slots,names[r.policy],r.runtime_median_ms.toFixed(1),pct(r.acceptance_rate_mean),pct(r.conflict_rate_mean),r.gap_mean_when_available==null?'未返回':pct(r.gap_mean_when_available),r.proven_optimal_instances+' / '+r.instances]);}
$('benchmark-distribution').onchange=renderBenchmark;
async function loadBenchmark(){try{benchmark=await api('/api/benchmark');$('benchmark-status').textContent=`已记录 ${benchmark.records.length/5} 个输入实例、${benchmark.records.length} 次策略运行；每次使用 ${benchmark.protocol.trials} 轮共同随机数验证，求解时限 ${benchmark.protocol.solver_time_limit_seconds} 秒。记录环境 ${benchmark.machine.system} / ${benchmark.machine.machine}。`;renderBenchmark();}catch(e){$('benchmark-status').textContent='规模实验记录暂不可用，可运行 scripts/benchmark.py 生成。';}}
for(const id of ['slots','risk','fixed-buffer','time-limit','trials','seed','distribution','objective'])$(id).addEventListener('change',()=>{if(result){result=null;reportText='';$('results').hidden=true;$('empty').hidden=false;$('run-meta').textContent='配置已改变，请重新计算';message('配置已改变，请重新计算');}});
init();loadBenchmark();
