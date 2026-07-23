# -*- coding: utf-8 -*-
"""HTML unico da listagem: dados embutidos + JS inline (sem rede externa).

Identidade visual = a MESMA do Painel de Compras (erp-bridge
src/templates/painel_compras.html) — manter as variaveis :root em dia.

Agrupamento de FILIAIS (dono, 23/07, UX revisada):
- lista principal: cada fornecedor tem uma FLAG (circulo) sempre visivel;
  marcou 2+ -> barra fixa "agrupar selecionados (N)" -> popup escolhe quem
  e a MAE entre os marcados (padrao: o de mais produtos);
- dentro do fornecedor: "definir mae" abre popup com a situacao atual
  (agrupa quem / sem grupo) + CAIXA DE PESQUISA com lista filtrada para
  relacionar a outro fornecedor (sem datalist nativo);
- "mover itens": marca linhas -> popup com a mesma caixa de pesquisa.
O DADOS embutido vai CRU; o JS aplica os overrides (grupos filho->mae +
itens movidos) — edicao vale na hora E persiste via POST
/listagem/overrides (servidor do painel), que o gerar.py reembute depois.

ARMADILHA conhecida: visualizador do WhatsApp nao executa JavaScript."""
import html as _html
import json

import formato

COTACAO = "COTACAO"
SEM_FORNECEDOR = "SEM FORNECEDOR"
MARCAS_TXT = {"*": "*", "novo": "novo", "sem_venda": "sem venda 6m",
              "ruptura_cronica": "ruptura crônica"}
MAX_RESULTADOS = 300   # busca por produto: teto de linhas exibidas


def preparar(por_fornecedor):
    """dict {fornecedor: [linhas]} -> lista ordenada p/ o template."""
    def chave_forn(nome):
        if nome == COTACAO:
            return (0, "")
        if nome == SEM_FORNECEDOR:
            return (2, "")
        return (1, nome)

    saida = []
    for nome in sorted(por_fornecedor, key=chave_forn):
        produtos = sorted(por_fornecedor[nome],
                          key=lambda p: (formato.ordem_rua(p["rua"]),
                                         p["nome"]))
        saida.append({"nome": nome, "qtd": len(produtos),
                      "produtos": produtos})
    return saida


def _blob(obj):
    # todo '<' vira a sequencia backslash-u003c: nenhum "</script>" nem
    # tag alguma consegue escapar dos blobs embutidos
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def montar(fornecedores, dados_de, overrides=None):
    dados = [{"nome": f["nome"], "qtd": f["qtd"],
              "produtos": [{"codigo": p["codigo"],
                            "nome": p["nome"],
                            "rua": p.get("rua_rotulo") or "",
                            "ro": p.get("ro", 999999),
                            "cx": p.get("cx_mae") or 1,
                            "mv": p.get("mv", 0),
                            "minimo": p["minimo"],
                            "marca": MARCAS_TXT.get(p.get("marca") or "", ""),
                            "rp": 1 if p.get("ruptura") else 0}
                           for p in f["produtos"]]}
             for f in fornecedores]
    ovr = overrides or {"grupos": {}, "itens": {}}
    return _TEMPLATE.replace("__DADOS__", _blob(dados)) \
                    .replace("__OVERRIDES__", _blob(ovr)) \
                    .replace("__DADOS_DE__", _html.escape(dados_de)) \
                    .replace("__MAX_RES__", str(MAX_RESULTADOS))


_TEMPLATE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Listagem por fornecedor</title>
<style>
 /* identidade do Painel de Compras (painel_compras.html) — manter em dia */
 :root { --bg:#0b0e13; --card:#141922; --card2:#0e1219; --borda:#232b38;
         --linha:#1a2029; --hover:#1b2331;
         --txt:#e8edf4; --mut:#8e99a8; --fraco:#5c6572;
         --ok:#3fb950; --warn:#d29922; --bad:#f85149; --acc:#58a6ff }
 * { box-sizing:border-box; margin:0 }
 ::selection { background:#2c4a75; color:#fff }
 body { background:var(--bg); color:var(--txt); padding-bottom:4rem;
        font:16px/1.45 "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif }
 body.arraste, body.arraste * { user-select:none }
 .miolo { max-width:68rem; margin:0 auto; padding:0 .85rem }
 header { position:sticky; top:0; z-index:2; background:var(--card);
          border-bottom:1px solid var(--borda); padding:.7rem 0 .8rem }
 header h1 { font:700 1.15rem/1.2 "Segoe UI Variable Display", "Segoe UI",
             system-ui, sans-serif; letter-spacing:-.01em }
 header small { color:var(--mut); font-size:.74rem;
                font-variant-numeric:tabular-nums }
 .buscas { display:flex; gap:.55rem; margin-top:.55rem }
 .buscas input { flex:1 1 50%; min-width:0; padding:.5rem .9rem; font-size:1rem;
          color:var(--txt); background:var(--card2);
          border:1px solid var(--borda); border-radius:999px; outline:none }
 .buscas input:focus { border-color:#3a5a8c }
 .acoes { display:flex; flex-wrap:wrap; gap:.55rem; margin:.8rem 0 .2rem }
 .acoes button, .pill { padding:.3rem .9rem; font-size:.85rem;
          color:var(--mut); background:var(--card2);
          border:1px solid var(--borda); border-radius:999px; cursor:pointer }
 .acoes button:hover, .pill:hover { border-color:#3a5a8c; color:var(--txt) }
 .acoes button.on { background:#1c3050; border-color:#3a5a8c; color:var(--txt) }
 #pdf, #pdfRes { color:var(--acc) }
 #lista { display:grid; gap:.55rem; padding-top:.8rem; padding-bottom:.8rem }
 .cartao { display:flex; align-items:center; gap:.6rem;
        background:var(--card); border:1px solid var(--borda);
        border-radius:14px; transition:border-color .15s }
 .cartao:hover { border-color:#31405a }
 .cartao.sel { background:#16233a; border-color:#3a5a8c }
 .flag { flex:none; width:1.35rem; height:1.35rem; margin-left:.7rem;
        border:2px solid var(--mut); border-radius:50%; cursor:pointer }
 .flag:hover { border-color:var(--acc) }
 .cartao.sel .flag { background:var(--acc); border-color:var(--acc) }
 .cartao button { flex:1 1 auto; display:flex; justify-content:space-between;
        align-items:center; gap:.7rem; text-align:left; min-width:0;
        padding:.65rem .85rem .65rem 0; color:var(--txt); background:none;
        border:none; cursor:pointer;
        font:600 .95rem/1.3 "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif }
 .cartao button b { font-weight:650; font-size:.72rem; color:var(--mut);
        background:var(--card2); border:1px solid var(--linha);
        border-radius:999px; padding:.02rem .55rem .08rem;
        font-variant-numeric:tabular-nums; flex:none }
 #titulo, #tituloRes { font:650 1.05rem/1.3 "Segoe UI Variable Display",
           "Segoe UI", system-ui, sans-serif; margin:.45rem 0 .1rem }
 .agrupa { color:var(--mut); font-size:.76rem; margin:0 0 .55rem }
 .tabela { background:var(--card); border:1px solid var(--borda);
           border-radius:14px; overflow:auto; margin:.55rem 0 1rem }
 table { width:100%; border-collapse:collapse; font-size:.89rem }
 th { text-align:left; color:var(--mut); font-size:.72rem; font-weight:650;
      text-transform:uppercase; letter-spacing:.07em; padding:.45rem .65rem .4rem;
      border-bottom:1px solid var(--borda); position:sticky; top:0;
      background:var(--card); z-index:1; white-space:nowrap }
 th.ord { cursor:pointer; user-select:none }
 th.ord:hover { color:var(--txt) }
 td { padding:.34rem .65rem; border-bottom:1px solid var(--linha);
      white-space:nowrap }
 tr:last-child td { border-bottom:none }
 td.desc { white-space:normal; width:99% }
 th.num, td.num { text-align:right; font-variant-numeric:tabular-nums }
 tr:nth-child(even) td { background:rgba(255,255,255,.015) }
 tr:hover td { background:var(--hover) }
 tr.link, tr.selv { cursor:pointer }
 tr.selv.on td { background:#1c3050 }
 td.chk { color:var(--acc); width:1.6rem; text-align:center }
 .cod { color:var(--mut); font-variant-numeric:tabular-nums }
 .forn { color:var(--mut); font-size:.82rem }
 .marca { border-radius:999px; padding:.08rem .55rem .12rem; font-size:.76rem;
          font-weight:400; white-space:nowrap; background:#2a3140;
          border:1px solid #39424f; color:#b6c2d0 }
 .minimo { font-weight:650 }
 th.mao { color:var(--mut) }
 td.mao { min-width:4rem }
 #barra { position:fixed; left:0; right:0; bottom:0; z-index:3;
          background:var(--card); border-top:1px solid var(--borda);
          padding:.6rem .85rem; display:none; gap:.55rem; flex-wrap:wrap;
          justify-content:center; align-items:center }
 #barra .dica { color:var(--mut); font-size:.8rem }
 #barra button { font-size:.95rem; padding:.45rem 1.1rem }
 #dlg { position:fixed; inset:0; z-index:4; display:none;
        background:rgba(0,0,0,.55); align-items:center; justify-content:center }
 #dlg .caixa { background:var(--card); border:1px solid var(--borda);
        border-radius:14px; padding:1rem; width:min(28rem, 92vw) }
 #dlg h3 { font-size:1rem; margin-bottom:.45rem }
 #dlg .situacao { color:var(--mut); font-size:.82rem; margin-bottom:.7rem }
 #dlg input { width:100%; padding:.5rem .8rem; font-size:1rem;
        color:var(--txt); background:var(--card2);
        border:1px solid var(--borda); border-radius:10px; outline:none }
 #dlg input:focus { border-color:#3a5a8c }
 #dlgLista { max-height:11rem; overflow:auto; margin-top:.5rem;
        border:1px solid var(--linha); border-radius:10px }
 #dlgLista div { padding:.42rem .7rem; cursor:pointer; font-size:.9rem;
        border-bottom:1px solid var(--linha) }
 #dlgLista div:last-child { border-bottom:none }
 #dlgLista div:hover { background:var(--hover) }
 #dlgLista div.on { background:#1c3050; color:var(--txt) }
 #dlgLista div small { color:var(--fraco); margin-left:.4rem }
 #dlg .botoes { display:flex; flex-wrap:wrap; gap:.55rem; margin-top:.8rem;
        justify-content:flex-end }
 #dlg .botoes button { padding:.4rem 1rem; border-radius:999px; cursor:pointer;
        background:var(--card2); color:var(--txt);
        border:1px solid var(--borda) }
 #dlg .botoes .ok { background:#1c3050; border-color:#3a5a8c }
 #toast { position:fixed; bottom:4.2rem; left:50%; transform:translateX(-50%);
        background:#12351c; color:#56d364; border:1px solid #1f5a30;
        border-radius:999px; padding:.35rem 1rem; font-size:.85rem;
        display:none; z-index:5 }
 .soprint { display:none }
 footer { color:var(--mut); font-size:.76rem; line-height:1.6;
          padding-bottom:1rem }
 @media print {
   body { background:#fff; color:#000; padding-bottom:0;
          font:12px/1.35 "Segoe UI", system-ui, sans-serif }
   header, footer, .acoes, #lista, #barra, #dlg, #toast { display:none !important }
   .nao-imprime { display:none !important }
   .miolo { max-width:none; padding:0 }
   .soprint { display:block; color:#333; font-size:11px; margin:0 0 6px }
   #titulo, #tituloRes { color:#000; margin:6px 0 }
   .agrupa { display:none }
   .tabela { border:none; border-radius:0; overflow:visible }
   th { position:static; background:#fff !important; color:#000;
        border-bottom:1px solid #999 }
   td { background:#fff !important; color:#000; border-color:#ccc }
   td.cod, .forn { color:#333 }
   tr:nth-child(even) td { background:#f3f3f3 !important }
   .rupt, .marca { display:none !important }
   th.mao { color:#333 }
 }
</style></head><body>
<header><div class="miolo"><h1>Listagem por fornecedor</h1>
<small>dados de __DADOS_DE__</small>
<div class="buscas">
<input id="busca" type="search" placeholder="buscar fornecedor...">
<input id="buscaProd" type="search" placeholder="buscar produto...">
</div>
</div></header>
<div class="miolo">
<div id="telaLista">
 <div class="acoes nao-imprime">
  <button id="btnTodosForn" title="marca/desmarca todos os fornecedores vis&iacute;veis (respeita a busca)">&#9711; marcar todos os vis&iacute;veis</button>
 </div>
 <div id="lista"></div>
</div>
<div id="detalhe" style="display:none">
 <div class="acoes nao-imprime">
  <button id="volta">&larr; fornecedores</button>
  <button id="pdf" title="imprimir / salvar em PDF">&#128424; salvar PDF</button>
  <button id="btnMae" title="relacionar este fornecedor a outro">&#128279; atrelar ao fornecedor m&atilde;e</button>
  <button id="btnMover" title="mandar itens para outro fornecedor">&#9745; mover itens</button>
 </div>
 <h2 id="titulo"></h2>
 <div class="agrupa" id="agrupaInfo"></div>
 <div class="soprint">dados de __DADOS_DE__ &middot; AtacadeRJ</div>
 <div class="tabela"><table><thead><tr id="cabDet">
 <th class="ord" data-k="codigo" data-rot="c&oacute;digo">c&oacute;digo</th>
 <th class="ord" data-k="nome" data-rot="produto">produto</th>
 <th class="ord" data-k="ro" data-rot="corredor">corredor</th>
 <th class="num ord" data-k="cx" data-rot="cx m&atilde;e">cx m&atilde;e</th>
 <th class="num ord" data-k="mv" data-rot="est. m&iacute;nimo">est. m&iacute;nimo</th>
 <th class="mao">data __/__/__</th><th class="mao">data __/__/__</th>
 <th class="mao">data __/__/__</th><th class="mao">data __/__/__</th>
 </tr></thead><tbody id="corpo"></tbody></table></div>
</div>
<div id="resultados" style="display:none">
 <div class="acoes nao-imprime">
  <button id="voltaRes">&larr; fornecedores</button>
  <button id="pdfRes" title="imprimir / salvar em PDF">&#128424; salvar PDF</button>
 </div>
 <h2 id="tituloRes"></h2>
 <div class="soprint">dados de __DADOS_DE__ &middot; AtacadeRJ</div>
 <div class="tabela"><table><thead><tr id="cabRes">
 <th class="ord" data-k="codigo" data-rot="c&oacute;digo">c&oacute;digo</th>
 <th class="ord" data-k="nome" data-rot="produto">produto</th>
 <th class="ord" data-k="forn" data-rot="fornecedor">fornecedor</th>
 <th class="ord" data-k="ro" data-rot="corredor">corredor</th>
 <th class="num ord" data-k="cx" data-rot="cx m&atilde;e">cx m&atilde;e</th>
 <th class="num ord" data-k="mv" data-rot="est. m&iacute;nimo">est. m&iacute;nimo</th>
 </tr></thead><tbody id="corpoRes"></tbody></table></div>
</div>
<footer>&#9888;&#65039; = poss&iacute;vel ruptura AGORA (detector de estoque) &middot;
 * = calculado com ruptura (pode estar subestimado) &middot;
 novo = estimativa proporcional (produto recente) &middot;
 sem venda 6m / ruptura cr&ocirc;nica = sem base de venda (m&iacute;nimo = piso de 1 cx/un) &middot;
 cx m&atilde;e = unidades por caixa (1 = sem caixa) &middot;
 &#9711; = marque fornecedor(es) e use "agrupar ao m&atilde;e" (ou deixar solto)</footer>
</div>
<div id="barra"></div>
<div id="dlg"><div class="caixa">
 <h3 id="dlgTitulo"></h3>
 <div class="situacao" id="dlgSituacao"></div>
 <input id="dlgBusca" type="search" placeholder="pesquisar fornecedor...">
 <div id="dlgLista"></div>
 <div class="botoes">
  <button id="dlgDesagrupar">desagrupar</button>
  <button id="dlgCancelar">cancelar</button>
  <button id="dlgOk" class="ok">salvar</button>
 </div>
</div></div>
<div id="toast"></div>
<script>
var BRUTO = __DADOS__, OVR = __OVERRIDES__, MAX_RES = __MAX_RES__;
var DADOS = [], MEMBROS = {};
var abertoNome = null, modoItem = false;
var selForn = {}, selItem = {};
var $ = function(id){return document.getElementById(id);};
function esc(s){var d=document.createElement('div');
  d.appendChild(document.createTextNode(String(s)));return d.innerHTML;}

/* ---- ordenacao por coluna: 1o clique asc, 2o desc, 3o volta ao padrao */
var ordDet={k:'',dir:1}, ordRes={k:'',dir:1};
function sortLista(ps, ord, forn){
  var arr=ps.slice();
  if(!ord.k)return arr.sort(function(a,b){
    return a.ro-b.ro || a.nome.localeCompare(b.nome);});
  return arr.sort(function(a,b){
    var va=(ord.k==='forn')?(forn?forn(a):''):(ord.k==='nome'?a.nome:a[ord.k]||0);
    var vb=(ord.k==='forn')?(forn?forn(b):''):(ord.k==='nome'?b.nome:b[ord.k]||0);
    if(typeof va==='string')return ord.dir*String(va).localeCompare(String(vb));
    return ord.dir*(va-vb);});
}
function pintarSetas(idCab, ord){
  var ths=$(idCab).querySelectorAll('th[data-k]');
  for(var i=0;i<ths.length;i++){
    var k=ths[i].getAttribute('data-k');
    ths[i].innerHTML=ths[i].getAttribute('data-rot')+
      (ord.k===k?(ord.dir>0?' \\u25b2':' \\u25bc'):'');
  }
}
function ligaOrdenacao(idCab, ord, rerender){
  $(idCab).addEventListener('click', function(e){
    var k=e.target.getAttribute && e.target.getAttribute('data-k');
    if(!k)return;
    if(ord.k===k){ if(ord.dir===1)ord.dir=-1; else {ord.k='';ord.dir=1;} }
    else { ord.k=k; ord.dir=1; }
    rerender();});
}

/* ---- overrides: resolve filho->mae (com corrente e trava de ciclo) ---- */
function resolve(nome){
  var v=nome, i=0;
  while(OVR.grupos[v] && i++<10){ v=OVR.grupos[v]; if(v===nome)break; }
  return v;
}
function aplicar(){
  var porForn={}, membros={};
  BRUTO.forEach(function(f){
    f.produtos.forEach(function(p){
      var destino = OVR.itens[String(p.codigo)] || f.nome;
      var fin = resolve(destino);
      (porForn[fin]=porForn[fin]||[]).push(p);
      if(fin!==f.nome){(membros[fin]=membros[fin]||{})[f.nome]=1;}
    });
  });
  var nomes=Object.keys(porForn).sort(function(a,b){
    var ka=(a==='COTACAO')?0:(a==='SEM FORNECEDOR')?2:1;
    var kb=(b==='COTACAO')?0:(b==='SEM FORNECEDOR')?2:1;
    return ka-kb || a.localeCompare(b);});
  DADOS=nomes.map(function(n){
    var ps=porForn[n].slice().sort(function(a,b){
      return a.ro-b.ro || a.nome.localeCompare(b.nome);});
    return {nome:n, qtd:ps.length, produtos:ps};});
  MEMBROS=membros;
}

/* ---- persistencia ---- */
function salvar(cb){
  fetch('/listagem/overrides',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(OVR)})
   .then(function(r){return r.json();})
   .then(function(j){if(!j.ok)throw 0; toast('salvo \\u2713'); cb&&cb();})
   .catch(function(){alert('N\\u00c3O salvou \\u2014 abra a p\\u00e1gina pelo endere\\u00e7o do ponte (porta 8477)');});
}
function toast(m){var t=$('toast');t.textContent=m;t.style.display='block';
  setTimeout(function(){t.style.display='none';},1800);}

/* ---- vistas ---- */
function mostra(alvo){
  $('telaLista').style.display=(alvo==='lista')?'block':'none';
  $('detalhe').style.display=(alvo==='det')?'block':'none';
  $('resultados').style.display=(alvo==='res')?'block':'none';
}
function celProduto(p){
  return (p.rp?'<span class="rupt" title="poss\\u00edvel ruptura">\\u26a0\\ufe0f</span> ':'')+
         esc(p.nome)+
         (p.marca?' <span class="marca">'+esc(p.marca)+'</span>':'');
}
/* lista principal: FLAG sempre visivel (marca -> barra aparece) */
function renderLista(filtro){
  var el=$('lista'); el.innerHTML='';
  DADOS.forEach(function(f){
    if(filtro && f.nome.toUpperCase().indexOf(filtro.toUpperCase())<0)return;
    var c=document.createElement('div');
    c.className='cartao'+(selForn[f.nome]?' sel':'');
    var fl=document.createElement('span');
    fl.className='flag'; fl.title='marcar para agrupar';
    fl.onclick=function(e){e.stopPropagation();
      if(selForn[f.nome])delete selForn[f.nome];
      else selForn[f.nome]=true;
      renderLista(filtro); renderBarra();};
    var b=document.createElement('button');
    b.innerHTML=esc(f.nome)+' <b>'+f.qtd+'</b>';
    b.onclick=function(){abrir(f.nome);};
    c.appendChild(fl); c.appendChild(b);
    el.appendChild(c);});
}
function abrir(nome){
  var f=null;
  DADOS.forEach(function(x){if(x.nome===nome)f=x;});
  if(!f){nome=resolve(nome);
    DADOS.forEach(function(x){if(x.nome===nome)f=x;});}
  if(!f)return;
  abertoNome=nome;
  $('titulo').textContent=f.nome+' \\u2014 '+f.qtd+' produtos';
  var ms=Object.keys(MEMBROS[nome]||{});
  $('agrupaInfo').textContent=ms.length?('agrupa: '+ms.join(' \\u00b7 ')):'';
  var corpo=$('corpo'); corpo.innerHTML='';
  sortLista(f.produtos, ordDet).forEach(function(p){
    var tr=document.createElement('tr');
    var chk=modoItem?('<td class="chk nao-imprime">'+
      (selItem[p.codigo]?'\\u2611':'\\u2610')+'</td>'):'';
    tr.innerHTML=chk+'<td class="cod">'+esc(p.codigo)+'</td><td class="desc">'+
      celProduto(p)+'</td><td>'+esc(p.rua)+
      '</td><td class="num">'+esc(p.cx)+
      '</td><td class="num minimo">'+esc(p.minimo)+'</td>'+
      '<td class="mao"></td>'.repeat(4);
    if(modoItem){tr.className='selv'+(selItem[p.codigo]?' on':'');
      // toque marca; segurar e ARRASTAR marca varios de uma vez (dono)
      tr.onmousedown=function(e){e.preventDefault();
        window._drag=true; window._dragVal=!selItem[p.codigo];
        marcaItem(tr, p.codigo, window._dragVal);};
      tr.onmouseenter=function(){ if(window._drag)
        marcaItem(tr, p.codigo, window._dragVal); };}
    corpo.appendChild(tr);});
  pintarSetas('cabDet', ordDet);
  var cab=$('cabDet');
  var temChk=cab.firstChild && cab.firstChild.className==='chk nao-imprime';
  if(modoItem && !temChk){var th=document.createElement('th');
    th.className='chk nao-imprime'; cab.insertBefore(th, cab.firstChild);}
  if(!modoItem && temChk){cab.removeChild(cab.firstChild);}
  mostra('det');
}
function renderResultados(q){
  var Q=q.toUpperCase(), achados=[];
  DADOS.forEach(function(f){
    f.produtos.forEach(function(p){
      if(p.nome.toUpperCase().indexOf(Q)<0 &&
         String(p.codigo).indexOf(Q)<0)return;
      achados.push({p:p, forn:f.nome});});
  });
  var total=achados.length;
  var ps=achados.map(function(a){return a.p;});
  var fornDe={}; achados.forEach(function(a){fornDe[a.p.codigo]=a.forn;});
  ps=sortLista(ps, ordRes, function(p){return fornDe[p.codigo];});
  var corpoRes=$('corpoRes'); corpoRes.innerHTML='';
  var mostrar=ps.slice(0, MAX_RES);
  mostrar.forEach(function(p){
    var nomeF=fornDe[p.codigo];
    var tr=document.createElement('tr');
    tr.className='link';
    tr.title='abrir '+nomeF;
    tr.innerHTML='<td class="cod">'+esc(p.codigo)+'</td><td class="desc">'+
      celProduto(p)+'</td><td class="forn">'+esc(nomeF)+'</td><td>'+esc(p.rua)+
      '</td><td class="num">'+esc(p.cx)+
      '</td><td class="num minimo">'+esc(p.minimo)+'</td>';
    tr.onclick=function(){$('buscaProd').value=''; abrir(nomeF);};
    corpoRes.appendChild(tr);});
  $('tituloRes').textContent='produto: "'+q+'" \\u2014 '+total+
    ' resultado'+(total===1?'':'s')+
    (total>mostrar.length?' (mostrando '+mostrar.length+')':'');
  pintarSetas('cabRes', ordRes);
  mostra('res');
}

/* ---- marcar item (toque ou arrasto) sem re-renderizar a tabela ---- */
function marcaItem(tr, cod, val){
  if(val)selItem[cod]=true; else delete selItem[cod];
  tr.className='selv'+(val?' on':'');
  if(tr.cells[0] && tr.cells[0].className.indexOf('chk')>=0)
    tr.cells[0].textContent=val?'\\u2611':'\\u2610';
  renderBarra();
}
document.addEventListener('mouseup', function(){window._drag=false;});

/* ---- barra fixa: aparece quando ha selecao ---- */
function renderBarra(){
  var b=$('barra');
  var nf=Object.keys(selForn).length, ni=Object.keys(selItem).length;
  if(nf>0 && !modoItem){
    b.innerHTML='<button id="bDef" class="pill">\\ud83d\\udd17 agrupar ao m\\u00e3e ('+nf+')</button>'+
      '<button id="bCan" class="pill">limpar</button>';
    b.style.display='flex';
    $('bDef').onclick=function(){dlgGrupo(Object.keys(selForn));};
    $('bCan').onclick=function(){selForn={};renderLista($('busca').value);renderBarra();};
  } else if(modoItem){
    b.innerHTML=(ni?'<button id="bMov" class="pill">mover '+ni+' item(ns) para...</button>':
      '<span class="dica">toque ou ARRASTE nas linhas para marcar</span>')+
      '<button id="bTodos" class="pill">todos</button>'+
      '<button id="bNenhum" class="pill">nenhum</button>'+
      '<button id="bCan" class="pill">cancelar</button>';
    b.style.display='flex';
    if(ni)$('bMov').onclick=dlgItens;
    $('bTodos').onclick=function(){
      DADOS.forEach(function(f){ if(f.nome!==abertoNome)return;
        f.produtos.forEach(function(p){selItem[p.codigo]=true;});});
      abrir(abertoNome); renderBarra();};
    $('bNenhum').onclick=function(){selItem={};abrir(abertoNome);renderBarra();};
    $('bCan').onclick=function(){modoItem=false;selItem={};
      document.body.className='';
      $('btnMover').className='';renderBarra();abrir(abertoNome);};
  } else b.style.display='none';
}

/* ---- dialogo com CAIXA DE PESQUISA (sem datalist nativo) ---- */
var dlgModo='', dlgEscolha='', dlgNomes=[];
function dlgOpcoes(filtro, fonte){
  var el=$('dlgLista'); el.innerHTML='';
  var Q=(filtro||'').toUpperCase(), n=0;
  fonte.forEach(function(o){
    if(Q && o.nome.toUpperCase().indexOf(Q)<0)return;
    if(n++>=60)return;
    var d=document.createElement('div');
    d.innerHTML=esc(o.nome)+(o.extra?'<small>'+esc(o.extra)+'</small>':'');
    if(o.nome===dlgEscolha)d.className='on';
    d.onclick=function(){dlgEscolha=o.nome;dlgOpcoes(filtro,fonte);};
    el.appendChild(d);});
  if(!n){el.innerHTML='<div><small>nada encontrado</small></div>';}
}
function dlgGrupo(nomes){
  dlgModo='grupo'; dlgNomes=nomes;
  $('dlgTitulo').textContent='Agrupar ao m\\u00e3e \\u2014 quem \\u00e9 a m\\u00e3e?';
  $('dlgSituacao').textContent='marcados: '+nomes.join(' \\u00b7 ');
  // marcados primeiro (candidatos naturais), depois TODOS os outros —
  // pesquisavel: da p/ agrupar 1 marcado a qualquer mae (dono, 23/07)
  var marcados=[], resto=[], maior='', q=-1;
  DADOS.forEach(function(f){
    if(nomes.indexOf(f.nome)>=0){
      marcados.push({nome:f.nome, extra:f.qtd+' produtos \\u00b7 marcado'});
      if(f.qtd>q){q=f.qtd;maior=f.nome;}
    } else resto.push({nome:f.nome, extra:f.qtd+' produtos'});});
  var fonte=marcados.concat(resto);
  dlgEscolha=(nomes.length>1)?maior:'';
  $('dlgBusca').value=''; $('dlgBusca').style.display='';
  $('dlgDesagrupar').style.display='';
  $('dlgDesagrupar').textContent='deixar solto';
  dlgOpcoes('', fonte); window._dlgFonte=fonte;
  $('dlg').style.display='flex';
  if(nomes.length===1)$('dlgBusca').focus();
}
function dlgMae(){
  dlgModo='mae'; dlgNomes=[abertoNome];
  $('dlgTitulo').textContent='Atrelar '+abertoNome+' a qual fornecedor m\\u00e3e?';
  var ms=Object.keys(MEMBROS[abertoNome]||{});
  $('dlgSituacao').textContent=ms.length?
    ('hoje \\u00e9 M\\u00c3E de: '+ms.join(' \\u00b7 ')):'hoje: sem grupo';
  var fonte=DADOS.filter(function(f){return f.nome!==abertoNome;})
    .map(function(f){return {nome:f.nome, extra:f.qtd+' produtos'};});
  dlgEscolha='';
  $('dlgBusca').value=''; $('dlgBusca').style.display='';
  $('dlgDesagrupar').style.display=ms.length?'':'none';
  $('dlgDesagrupar').textContent='desfazer grupo';
  dlgOpcoes('', fonte); window._dlgFonte=fonte;
  $('dlg').style.display='flex'; $('dlgBusca').focus();
}
function dlgItens(){
  dlgModo='itens';
  var m=Object.keys(selItem).length;
  $('dlgTitulo').textContent='Mover '+m+' item(ns) para qual fornecedor?';
  $('dlgSituacao').textContent='c\\u00f3digos: '+Object.keys(selItem).join(', ');
  var fonte=DADOS.filter(function(f){return f.nome!==abertoNome;})
    .map(function(f){return {nome:f.nome, extra:f.qtd+' produtos'};});
  dlgEscolha='';
  $('dlgBusca').value=''; $('dlgBusca').style.display='';
  $('dlgDesagrupar').style.display='none';
  dlgOpcoes('', fonte); window._dlgFonte=fonte;
  $('dlg').style.display='flex'; $('dlgBusca').focus();
}
$('dlgBusca').oninput=function(){dlgOpcoes(this.value, window._dlgFonte||[]);};
$('dlgCancelar').onclick=function(){$('dlg').style.display='none';};
$('dlgDesagrupar').onclick=function(){
  if(dlgModo==='grupo'){
    dlgNomes.forEach(function(n){delete OVR.grupos[n];});
  } else if(dlgModo==='mae'){
    // desfaz o grupo deste fornecedor: solta todos os filhos dele
    Object.keys(OVR.grupos).forEach(function(k){
      if(resolve(k)===abertoNome)delete OVR.grupos[k];});
  }
  $('dlg').style.display='none';
  salvar(function(){aplicar();selForn={};renderBarra();
    renderLista($('busca').value);
    if(abertoNome && $('detalhe').style.display!=='none')abrir(abertoNome);});
};
$('dlgOk').onclick=function(){
  if(!dlgEscolha)return;
  var alvo=dlgEscolha;
  if(dlgModo==='grupo'){
    dlgNomes.forEach(function(n){if(n!==alvo)OVR.grupos[n]=alvo;});
    Object.keys(OVR.grupos).forEach(function(k){
      if(dlgNomes.indexOf(OVR.grupos[k])>=0 && OVR.grupos[k]!==alvo)
        OVR.grupos[k]=alvo;});
    delete OVR.grupos[alvo];             // mae nao pode ser filha
  } else if(dlgModo==='mae'){
    OVR.grupos[abertoNome]=alvo;
    Object.keys(OVR.grupos).forEach(function(k){
      if(OVR.grupos[k]===abertoNome && k!==abertoNome)OVR.grupos[k]=alvo;});
    delete OVR.grupos[alvo];
  } else {
    Object.keys(selItem).forEach(function(c){OVR.itens[c]=alvo;});
  }
  $('dlg').style.display='none';
  var destino=resolve(alvo);
  salvar(function(){aplicar();
    selForn={}; renderBarra();
    if(dlgModo==='itens'){modoItem=false;selItem={};
      document.body.className='';
      $('btnMover').className='';abrir(abertoNome||destino);}
    else if(dlgModo==='mae'){abrir(destino);}
    else {renderLista($('busca').value);mostra('lista');}});
};

/* ---- botoes fixos ---- */
$('btnTodosForn').onclick=function(){
  var filtro=($('busca').value||'').toUpperCase();
  var visiveis=DADOS.filter(function(f){
    return !filtro || f.nome.toUpperCase().indexOf(filtro)>=0;});
  var todosJa=visiveis.length && visiveis.every(function(f){
    return selForn[f.nome];});
  visiveis.forEach(function(f){
    if(todosJa)delete selForn[f.nome]; else selForn[f.nome]=true;});
  renderLista($('busca').value); renderBarra();};
$('btnMae').onclick=function(){if(abertoNome)dlgMae();};
$('btnMover').onclick=function(){
  modoItem=!modoItem; selItem={};
  this.className=modoItem?'on':'';
  document.body.className=modoItem?'arraste':'';
  abrir(abertoNome); renderBarra();};
$('volta').onclick=function(){modoItem=false;selItem={};
  document.body.className='';
  $('btnMover').className='';renderBarra();mostra('lista');};
$('voltaRes').onclick=function(){$('buscaProd').value='';mostra('lista');};
$('pdf').onclick=function(){window.print();};
$('pdfRes').onclick=function(){window.print();};
$('busca').oninput=function(){
  $('buscaProd').value=''; mostra('lista'); renderLista(this.value);};
$('buscaProd').oninput=function(){
  var q=this.value.trim();
  if(q.length>=2){renderResultados(q);}
  else{mostra('lista');renderLista($('busca').value);}
};

/* ---- arranque: aplica o embutido e busca a versao fresca no servidor ---- */
ligaOrdenacao('cabDet', ordDet, function(){if(abertoNome)abrir(abertoNome);});
ligaOrdenacao('cabRes', ordRes, function(){
  renderResultados($('buscaProd').value.trim());});
aplicar(); renderLista('');
fetch('/listagem/overrides').then(function(r){return r.json();})
 .then(function(j){ if(j && j.grupos){OVR=j; aplicar();
   renderLista($('busca').value);} })
 .catch(function(){});
</script></body></html>
"""
