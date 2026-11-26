import { esc } from './nucleo.js';
export const PLANO={nome:'Comparação A–D no PC',objetivo:'Medir percepção e comunicação em simulação parada',hipotese:'H3',configuracoes:['A','B','C','D'],duracao_s:5,aquecimento_s:1,repeticoes:5,semente:7};
export const NOMES={A:'OpenCV embarcado virtual',B:'CNN embarcada virtual · diagnóstico',C:'OpenCV distribuído virtual',D:'CNN distribuída virtual · diagnóstico'};
export function matriz(rows,metrica='inferencia_s') {
  return ['A','B','C','D'].map(k=>{const v=rows.filter(r=>r.configuracao===k&&r.estado==='concluida').map(r=>r.resultado?.metricas?.[metrica]?.media).filter(v=>typeof v==='number'&&Number.isFinite(v));return {configuracao:k,repeticoes:v.length,media:v.length?v.reduce((a,b)=>a+b,0)/v.length:null};});
}
const n=v=>v==null?'Indisponível':Number(v).toPrecision(4);
export function graficoComparacao(itens,metrica,origem='simulada',nivel=3){
  const max=Math.max(...itens.map(v=>v.media??0),1e-12);
  if(!itens.some(v=>v.n))return '<p>Sem medições para gerar gráfico.</p>';
  return `<svg id="grafico-ciencia" class="chart" viewBox="0 0 800 300" role="img" aria-label="Médias por execução"><text x="20" y="25" fill="currentColor">${esc(metrica)} · médias por execução · ${esc(origem)} · nível ${esc(nivel)}</text>${itens.map((v,i)=>{const w=Math.max(0,v.media/max*440);return `<text x="20" y="${65+i*50}" fill="currentColor">${esc(v.configuracao)} · n=${v.n}</text><rect x="115" y="${45+i*50}" width="${w}" height="28" fill="#24aab4"/><text x="${125+w}" y="${65+i*50}" fill="currentColor">${n(v.media)}</text>`;}).join('')}<text x="20" y="285" fill="currentColor">Unidade indicada na métrica. Não demonstra superioridade física.</text></svg><button data-export="grafico-ciencia" data-formato="svg">Exportar comparação SVG</button><button data-export="grafico-ciencia" data-formato="png">Exportar comparação PNG</button>`;
}
export function htmlCiencia(){return `<section class="panel" id="ciencia"><span class="eyebrow">ETAPA 7 · MÉTODO EXPERIMENTAL</span><h2>Da sessão à evidência</h2><p>Configure, repita e compare medições identificadas. A execução automática usa somente o simulador parado; resultados do PC não representam a Raspberry física.</p><div class="grid2"><form id="plano-ciencia" class="form-grid"><label class="full">Plano reproduzível (JSON)<textarea name="plano" rows="10" spellcheck="false">${esc(JSON.stringify(PLANO,null,2))}</textarea></label><button>Executar ensaio simulado</button><button type="button" id="cancelar-ciencia">Cancelar coleta</button></form><div><h3>Execução e rastreabilidade</h3><p id="progresso-ciencia" role="status">Consultando…</p><p class="note">Uma execução é uma repetição independente. Aquecimento e carga do modelo ficam separados. H1–H8 permanecem em investigação.</p><details><summary>Configurações e limites</summary><p>A: OpenCV local virtual · B: CNN local virtual · C: OpenCV remoto · D: CNN remota. Mesmo JPEG de 480×640 pixels. CNN sem autorização para navegação; RL depende de checkpoints.</p></details></div></div><div class="divider"></div><form id="filtro-ciencia" class="form-grid"><label>Experimento<select name="experimento" id="escolha-ciencia"><option value="">Todos</option></select></label><label>Origem<select name="origem"><option value="">Todas</option><option value="simulada">Simulada</option><option value="real">Real</option></select></label><label>Nível<select name="nivel"><option value="">Todos</option><option value="1">Unitário / isolado</option><option value="2">Integração</option><option value="3">Simulação</option><option value="4">Bancada</option><option value="5">Pista</option></select></label><label>Categoria<select name="categoria"><option value="">Todas</option><option value="benchmark_integrado">Benchmark integrado</option><option value="benchmark_isolado_offline">Benchmark isolado</option><option value="experimento_completo">Experimento completo</option></select></label><button>Consultar resultados</button></form><div class="table-wrap" id="execucoes-ciencia"></div><div id="relatorio-ciencia"></div><h3>Comparar repetições</h3><form id="comparar-ciencia" class="form-grid"><label>Métrica<select name="metrica">${[['inferencia_s','Inferência (s)'],['ciclo_s','Ciclo de retorno (s)'],['cpu_pc_pct','CPU do processo PC (%)'],['rss_bytes','RAM do processo (bytes)'],['controle_hz','Controle (Hz)'],['rtt_s','RTT (s)']].map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select></label><button>Comparar experimento selecionado</button></form><div id="matriz-ciencia" class="table-wrap"></div><p id="comparacao-ciencia" class="note"></p></section><div class="divider"></div>`;}
export function montarCiencia(root,api,mensagem){
  if(!root||root.dataset.montado)return;root.dataset.montado='sim';let ocupado=false,experimentAtual='',filtroAnterior='';
  const $=s=>root.querySelector(s),url=(id,arquivo)=>'/api/central/artefato-experimental?'+new URLSearchParams({id,arquivo});
  const seguro=fn=>async e=>{e?.preventDefault();try{await fn(e);}catch(err){mensagem(err.message,true);}};
  async function atualizar(){
    if(ocupado||!root.isConnected)return;ocupado=true;
    try{
      const filtro=Object.fromEntries(new FormData($('#filtro-ciencia')));experimentAtual=filtro.experimento;
      const assinatura=JSON.stringify(filtro);
      if(assinatura!==filtroAnterior){$('#matriz-ciencia').innerHTML='';$('#comparacao-ciencia').textContent='';filtroAnterior=assinatura;}
      const d=await api.get('/api/central/execucoes?'+new URLSearchParams(filtro));if(!root.isConnected)return;
      const rows=d.itens,s=d.executor;
      $('#progresso-ciencia').textContent=`${s.estado} · ${s.concluidas}/${s.total} repetições processadas${s.configuracao?' · '+s.configuracao:''}${s.erro?' · '+s.erro:''}`;
      $('#plano-ciencia button').disabled=s.ativo;$('#cancelar-ciencia').disabled=!s.ativo;
      if(!experimentAtual){const opcoes=new Map(rows.map(r=>[r.experimento_id,r.configuracoes.nome]));$('#escolha-ciencia').innerHTML='<option value="">Todos</option>'+[...opcoes].map(([id,nome])=>`<option value="${esc(id)}">${esc(nome)} · ${id.slice(0,8)}</option>`).join('');}
      $('#execucoes-ciencia').innerHTML=rows.length?`<table><thead><tr><th>Configuração</th><th>Repetição</th><th>Origem / nível</th><th>Estado</th><th>Inferência (ms)</th><th>Evidências</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(NOMES[r.configuracao]??r.configuracao)}</td><td>${r.repeticao}</td><td>${esc(r.origem)} / ${r.nivel}</td><td>${esc(r.estado)}${r.resultado.erro?' · '+esc(r.resultado.erro):''}</td><td>${n(r.resultado.metricas?.inferencia_s?.media==null?null:r.resultado.metricas.inferencia_s.media*1000)}</td><td><button data-relatorio="${esc(r.id)}">Gerar relatório</button>${r.sessao_id?`<button data-reproduzir="${r.sessao_id}">Reproduzir</button>`:''}<a href="${url(r.id,'amostras.csv')}" download>CSV</a></td></tr>`).join('')}</tbody></table>`:'<div class="empty">Nenhuma execução nesta categoria. Dados ausentes não são zero.</div>';
    }finally{ocupado=false;}
  }
  $('#plano-ciencia').onsubmit=seguro(async()=>{await api.post('executar-experimento',JSON.parse($('#plano-ciencia textarea').value));await atualizar();});
  $('#cancelar-ciencia').onclick=seguro(async()=>{await api.post('cancelar-experimento',{});await atualizar();});
  $('#filtro-ciencia').onsubmit=seguro(atualizar);
  $('#comparar-ciencia').onsubmit=seguro(async()=>{
    if(!experimentAtual)throw Error('Selecione um experimento para garantir condições comparáveis.');
    const metrica=new FormData($('#comparar-ciencia')).get('metrica'),filtros=Object.fromEntries(new FormData($('#filtro-ciencia'))),d=await api.get('/api/central/comparacao-cientifica?'+new URLSearchParams({...filtros,experimento:experimentAtual,metrica}));
    $('#matriz-ciencia').innerHTML=`<table><thead><tr><th>Configuração</th><th>Repetições válidas</th><th>Média (${esc(metrica)})</th><th>Desvio entre execuções</th></tr></thead><tbody>${['A','B','C','D'].map(k=>{const v=d.itens.find(r=>r.configuracao===k);return `<tr><td>${esc(NOMES[k])}</td><td>${v?.n??0}</td><td>${n(v?.media)}</td><td>${n(v?.desvio_padrao)}</td></tr>`;}).join('')}</tbody></table>`;
    $('#comparacao-ciencia').innerHTML=esc(d.motivo??`${d.unidade_experimental}. ${d.conclusao}`)+(d.comparavel?graficoComparacao(d.itens,metrica,d.origem,d.nivel):'');
  });
  const gerarRelatorio=seguro(async e=>{
    const alvo=e.target.closest('[data-relatorio]');
    const d=await api.post('relatorio-experimental',{id:alvo.dataset.relatorio});if(!root.isConnected)return;
    $('#relatorio-ciencia').innerHTML=`<h3>Relatório com dados registrados</h3><p>${d.arquivos.filter(f=>!f.endsWith('.png')&&!f.endsWith('.svg')).map(f=>`<a href="${url(d.execucao,f)}" target="_blank" rel="noopener">${esc(f)}</a>`).join(' · ')}</p>${d.arquivos.filter(f=>f.endsWith('.png')).map(f=>`<figure><img style="max-width:100%" loading="lazy" alt="${esc(f)} · dados simulados do PC" src="${url(d.execucao,f)}"><figcaption><a href="${url(d.execucao,f.replace('.png','.svg'))}" download>Exportar SVG</a></figcaption></figure>`).join('')}`;
  });
  root.addEventListener('click',e=>{if(e.target.closest('[data-relatorio]'))gerarRelatorio(e);});
  root.querySelectorAll('button[type=submit], form > button:not([type])').forEach(b=>b.disabled=false);
  atualizar().catch(err=>mensagem(err.message,true));
  const timer=setInterval(()=>{if(!root.isConnected){clearInterval(timer);return;}atualizar().catch(err=>mensagem(err.message,true));},2000);
}
