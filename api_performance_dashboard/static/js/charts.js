
const sidebarItems = document.querySelectorAll(".icon-item");
const sections = document.querySelectorAll(".section");

const regionSel = document.getElementById('regionFilter');
const statusSel = document.getElementById('statusFilter');
const methodSel = document.getElementById('methodFilter');
const clientSel = document.getElementById('clientFilter');

const resetBtn  = document.getElementById('resetFilters');
const refreshBtn = document.getElementById('refreshNow');

const kpiTotal = document.getElementById('kpiTotal');
const kpiError = document.getElementById('kpiError');
const kpiAvg   = document.getElementById('kpiAvg');

const loading = document.getElementById('loading');

let charts = {};      

function qs(v){ return encodeURIComponent(v ?? ''); }
function currentFilters(){
  return {
    region: regionSel.value || '',
    status: statusSel.value || '',
    method: methodSel.value || '',
    client: clientSel.value || ''
  };
}
function buildQuery(params){
  const p = Object.entries(params).filter(([,v])=>v).map(([k,v])=>`${k}=${qs(v)}`).join('&');
  return p ? `?${p}` : '';
}
function showLoading(show=true){ loading.classList.toggle('hidden', !show); }

async function jget(url){
  const r = await fetch(url);
  if(!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function destroyChart(id){
  if(charts[id]){
    try{ charts[id].destroy(); }catch(e){}
    charts[id] = null;
  }
}

function createChart(canvasId, type, labels, data, opts={}){
  const el = document.getElementById(canvasId);
  if(!el) return;
  const ctx = el.getContext('2d');
  destroyChart(canvasId);

  const palette = (n) => {
    const base = ['#0ea5e9','#10b981','#f59e0b','#ef4444','#6366f1','#14b8a6','#84cc16','#f43f5e'];
    return Array.from({length:n}, (_,i)=> base[i % base.length]);
  };

  charts[canvasId] = new Chart(ctx, {
    type,
    data: {
      labels,
      datasets: [{
        label: opts.label || '',
        data,
        backgroundColor: type === 'line' ? 'rgba(37,99,235,0.12)' : palette(labels.length),
        borderColor: '#0b3b3a',
        borderWidth: type === 'line' ? 2 : 0,
        tension: 0.35,
        fill: type === 'line'
      }]
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { display: !!opts.legend },
        tooltip: { callbacks: opts.tooltips || {} }
      },
      scales: opts.scales || {
        x: { ticks:{ maxRotation:20, minRotation:0 }, grid:{ color: 'rgba(2,6,23,0.06)' } },
        y: { ticks:{ }, grid:{ color: 'rgba(2,6,23,0.06)' } }
      }
    }
  });
}

async function loadFilterOptions(){
  try{
    const [regions, statuses, methods, clients] = await Promise.all([
      jget('/api/regions'),
      jget('/api/statuscodes'),
      jget('/api/methods/list'),
      jget('/api/clients/list')
    ]);

    const fill = (el, arr, label) => {
      el.innerHTML = '';
      const all = document.createElement('option');
      all.value=''; all.textContent = `All ${label}`;
      el.appendChild(all);
      (arr || []).filter(x=>x!==null && x!==undefined && `${x}`.trim()!=='').forEach(v=>{
        const o = document.createElement('option'); o.value = v; o.textContent = v; el.appendChild(o);
      });
    };

    fill(regionSel, regions, 'Regions');
    fill(statusSel, statuses, 'Statuses');
    fill(methodSel, methods, 'Methods');
    fill(clientSel, clients, 'Clients');
  } catch(e){
    console.error('loadFilterOptions failed', e);
  }
}

async function loadSummary(){
  try{
    const q = buildQuery(currentFilters());
    const s = await jget(`/api/summary${q}`);
    kpiTotal.textContent = (s.total ?? 0).toLocaleString();
    kpiError.textContent = `${s.error_rate ?? 0}%`;
    kpiAvg.textContent = `${s.avg_response_time ?? 0} ms`;
  }catch(e){
    console.error('loadSummary', e);
  }
}

async function loadChartsOverview(){
  const q = buildQuery(currentFilters());
  try{
    const [c1,c2,c3,c4,c5,c6] = await Promise.all([
      jget(`/api/endpoint${q}`),
      jget(`/api/status${q}`),
      jget(`/api/response_time${q}`),
      jget(`/api/region${q}`),
      jget(`/api/methods${q}`),
      jget(`/api/clients${q}`)
    ]);

    createChart('endpointChart','bar', c1.labels, c1.counts, {legend:false});
    createChart('statusChart','doughnut', c2.labels, c2.counts, {legend:true});
    createChart('responseChart','line', c3.labels, c3.counts, {legend:false});
    createChart('regionChart','bar', c4.labels, c4.counts, {legend:false});
    createChart('methodChart','bar', c5.labels, c5.counts, {legend:false});
    createChart('clientChart','pie', c6.labels, c6.counts, {legend:true});
  } catch(e){
    console.error('loadChartsOverview', e);
  }
}


function clearHeatmap(){
  const el = document.getElementById('heatmap');
  el.innerHTML = '';
}

async function loadHeatmap(){
  showLoading(true);
  try{
    const windowHours = document.getElementById('heat_window') ? document.getElementById('heat_window').value : '24';
    const topRegions = document.getElementById('heat_top_regions') ? document.getElementById('heat_top_regions').value : '20';
    const q = `?hours=${qs(windowHours)}&top=${qs(topRegions)}`;

    const payload = await jget(`/api/heatmap${q}`);
    renderHeatmap(payload);
  } catch(err){
    console.error('loadHeatmap err', err);
    const el = document.getElementById('heatmap');
    el.innerHTML = '<div style="padding:18px;color:var(--muted)">Failed to load heatmap.</div>';
  } finally{
    showLoading(false);
  }
}

function renderHeatmap(data){
  // data: {regions:[], hours:[], matrix:[ [..], ... ], totals:[]}
  const container = document.getElementById('heatmap');
  container.innerHTML = ''; 

  if(!data || !data.regions || data.regions.length === 0){
    container.innerHTML = '<div style="padding:18px;color:var(--muted)">No heatmap data available.</div>';
    return;
  }

  // margins: increase bottom to make room for legend labels & axis title
  const margin = {top: 50, right: 18, bottom: 100, left: 160};
  const totalWidth = Math.max(760, container.clientWidth); 
  const innerWidth = totalWidth - margin.left - margin.right;
  const rowHeight = 34;
  const height = Math.max(300, data.regions.length * rowHeight); 

  const svg = d3.select(container).append('svg')
    .attr('width', totalWidth)
    .attr('height', height + margin.top + margin.bottom);

  const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

  const rows = data.regions;
  const cols = data.hours; 

  // flatten matrix to cell objects 
  const cells = [];
  for(let r=0;r<rows.length;r++){
    for(let c=0;c<cols.length;c++){
      const v = (data.matrix && data.matrix[r] && data.matrix[r][c]) ? data.matrix[r][c] : 0;
      cells.push({r, c, value: v, region: rows[r], hour: cols[c]});
    }
  }

  const maxV = d3.max(cells, d=>d.value) || 1;
  const minV = 0;
  const midV = Math.round(maxV / 2);

  const xScale = d3.scaleBand().domain(d3.range(cols.length)).range([0, innerWidth]).padding(0.06);
  const yScale = d3.scaleBand().domain(d3.range(rows.length)).range([0, height]).padding(0.12);


  const color = d3.scaleSequential().interpolator(d3.interpolateYlOrRd).domain([minV, maxV]);


  svg.append('g')
    .attr('transform', `translate(${margin.left}, ${margin.top - 12})`)
    .selectAll('text')
    .data(cols)
    .enter()
    .append('text')
    .attr('x', (_,i)=> xScale(i) + xScale.bandwidth()/2)
    .attr('y', -6)
    .attr('text-anchor', 'middle')
    .attr('font-size', 11)
    .attr('fill', '#334155')
    .text(d=>`${d}`);

  const yAxisGroup = svg.append('g')
    .attr('transform', `translate(${margin.left - 12}, ${margin.top})`);
  yAxisGroup.selectAll('text')
    .data(rows)
    .enter()
    .append('text')
    .attr('x', -8)
    .attr('y', (_,i)=> yScale(i) + yScale.bandwidth()/2 + 5)
    .attr('text-anchor', 'end')
    .attr('font-size', 13)
    .attr('fill', '#0f172a')
    .text(d=>d);

  
  const cellG = g.append('g');
  const rects = cellG.selectAll('rect')
    .data(cells)
    .enter()
    .append('rect')
    .attr('x', d => xScale(d.c))
    .attr('y', d => yScale(d.r))
    .attr('width', xScale.bandwidth())
    .attr('height', yScale.bandwidth())
    .attr('rx', 6)
    .attr('ry', 6)
    .attr('fill', d => d.value > 0 ? color(d.value) : '#f8fafc')
    .attr('stroke', '#ebf2f7')
    .attr('stroke-width', 1);

  
  const labels = cellG.selectAll('text.cell-label')
    .data(cells.filter(d => d.value !== 0))
    .enter()
    .append('text')
    .attr('class', 'cell-label')
    .attr('x', d => xScale(d.c) + xScale.bandwidth()/2)
    .attr('y', d => yScale(d.r) + yScale.bandwidth()/2 + 4)
    .attr('text-anchor', 'middle')
    .attr('font-size', 12)
    .attr('font-weight', 700)
    .text(d => d.value)
    .style('fill', d => {
      
      const t = d.value / (maxV || 1);
      return t > 0.55 ? '#ffffff' : '#0f172a';
    });

  
  d3.selectAll('.heat-tooltip').remove();
  const tooltip = d3.select('body').append('div')
    .attr('class','heat-tooltip')
    .style('position','absolute')
    .style('pointer-events','none')
    .style('padding','8px 10px')
    .style('background','rgba(255,255,255,0.98)')
    .style('box-shadow','0 6px 18px rgba(2,6,23,0.12)')
    .style('border-radius','8px')
    .style('font-family','Inter, system-ui, -apple-system, "Segoe UI", Roboto, Arial')
    .style('font-size','13px')
    .style('display','none');

  rects.on('mouseover', (event, d) => {
    tooltip.style('display','block');
    tooltip.html(`<b>${d.region}</b><br/>Hour: <b>${d.hour}</b><br/>Requests: <b>${d.value}</b>`);
    d3.select(event.currentTarget).attr('stroke','#0b3b3a').attr('stroke-width',1.6);
  }).on('mousemove', (event) => {
    tooltip.style('left', (event.pageX + 12) + 'px').style('top', (event.pageY + 12) + 'px');
  }).on('mouseleave', (event) => {
    tooltip.style('display','none');
    d3.select(event.currentTarget).attr('stroke','#ebf2f7').attr('stroke-width',1);
  }).on('click', (event,d) => {
    try{
      regionSel.value = d.region;
      (async ()=>{
        showLoading(true);
        await loadSummary();
        await loadChartsOverview();
        showLoading(false);
        
        document.querySelectorAll('.icon-item').forEach(i=>i.classList.remove('active'));
        const dashboardIcon = Array.from(document.querySelectorAll('.icon-item')).find(el=>el.dataset.section==='dashboard');
        if(dashboardIcon) dashboardIcon.classList.add('active');
        document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));
        const dashboardSec = document.getElementById('dashboard');
        if(dashboardSec) dashboardSec.classList.add('active');
      })();
    }catch(e){ console.error(e); }
  });

  
  const legendW = Math.min(innerWidth, 720);
  const legendX = margin.left + ((innerWidth - legendW) / 2);
  const legendY = margin.top + height + 20;

  const defs = svg.append('defs');
  const gradId = 'heatGrad';
  const grad = defs.append('linearGradient').attr('id', gradId);
  grad.append('stop').attr('offset','0%').attr('stop-color', color(minV));
  grad.append('stop').attr('offset','100%').attr('stop-color', color(maxV));

  const legendG = svg.append('g').attr('transform', `translate(${legendX}, ${legendY})`);

  legendG.append('rect')
    .attr('x', 0)
    .attr('y', 0)
    .attr('width', legendW)
    .attr('height', 14)
    .style('fill', `url(#${gradId})`)
    .style('stroke', '#e6eef6');

  
  const ticks = [minV, Math.round(midV), maxV];
  const tickX = [0, legendW/2, legendW];

  legendG.selectAll('text.legend-tick')
    .data(ticks)
    .enter()
    .append('text')
    .attr('class','legend-tick')
    .attr('x', (_,i) => tickX[i])
    .attr('y', 34)
    .attr('text-anchor', (_,i) => i===1 ? 'middle' : (i===2 ? 'end' : 'start'))
    .attr('font-size', 12)
    .attr('fill', '#334155')
    .text(d => String(d));

  
  legendG.append('text')
    .attr('x', legendW/2)
    .attr('y', 58)
    .attr('text-anchor','middle')
    .attr('font-size', 12)
    .attr('fill', '#475569')
    .text('Requests (color scale)');

  
  svg.append('text')
    .attr('x', margin.left + innerWidth/2)
    .attr('y', margin.top - 32)
    .attr('text-anchor','middle')
    .attr('font-size', 13)
    .attr('fill', '#475569')
    .text('Hour of day (0–23)');

  svg.append('text')
    .attr('transform', `translate(${margin.left - 120}, ${margin.top + height/2}) rotate(-90)`)
    .attr('text-anchor','middle')
    .attr('font-size', 13)
    .attr('fill', '#475569')
    .text('Region');

  d3.selectAll('.heat-tooltip').remove();
}




async function refreshAll(){
  try{
    showLoading(true);
    await loadSummary();
    await loadChartsOverview();
    
    if(document.getElementById('live').classList.contains('active')) {
      await loadHeatmap();
    }
  } catch(e){
    console.error('refreshAll error', e);
  } finally{
    showLoading(false);
  }
}

sidebarItems.forEach(item=>{
  item.addEventListener('click', ()=>{
    sidebarItems.forEach(i=>i.classList.remove('active'));
    item.classList.add('active');

    const target = item.dataset.section;
    sections.forEach(sec=>sec.classList.remove('active'));
    const el = document.getElementById(target);
    if(el) el.classList.add('active');

    if(target === 'dashboard') loadChartsOverview();
    else if (target === 'live') loadHeatmap();
  });
});

[regionSel, statusSel, methodSel, clientSel].forEach(el=>{
  el.addEventListener('change', refreshAll);
});
resetBtn.addEventListener('click', ()=>{
  regionSel.value = '';
  statusSel.value = '';
  methodSel.value = '';
  clientSel.value = '';
  refreshAll();
});
refreshBtn.addEventListener('click', refreshAll);


const heatRefresh = document.getElementById('heat_refresh');
if(heatRefresh){
  heatRefresh.addEventListener('click', loadHeatmap);
}

window.addEventListener('load', async ()=>{
  await loadFilterOptions();
  await refreshAll();
});




  