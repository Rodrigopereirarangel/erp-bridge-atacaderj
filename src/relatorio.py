# -*- coding: utf-8 -*-
"""HTML unico da listagem: dados embutidos + JS inline (sem rede externa).

Identidade visual = a MESMA do Painel de Compras (erp-bridge
src/templates/painel_compras.html) — manter as variaveis :root em dia.

Agrupamento de FILIAIS (dono, 23/07): fornecedores com nomes praticamente
iguais (COCA COLA / COCA COLA RJ ANDINA...) viram UM, com o nome da MAE
(quem mais recebe mercadoria). O DADOS embutido vai CRU; quem aplica os
overrides (grupos filho->mae + itens movidos a mao) e o JS — assim a
edicao na pagina vale na hora E persiste: POST /listagem/overrides no
servidor do painel grava o JSON que o gerar.py reembute na proxima geracao.
So ha UMA implementacao da regra (JS); o Python so transporta.

Piso do minimo (dono, 23/07) e aplicado no gerar.py; aqui so exibicao.

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
 body { background:var(--bg); color:var(--txt); padding-bottom:4rem;
        font:16px/1.45 "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif }
 .miolo { max-width:68rem; margin:0 auto; padding:0 .85rem }
 header { position:sticky; top:0; z-index:2; background:var(--card);
          border-bottom:1px solid var(--borda); padding:.7rem 0 .8rem }
 header h1 { font:700 1.15rem/1.2 "Segoe UI Variable Display", "Segoe UI",
             system-ui, sans-serif; letter-spacing:-.01em }
 header small { color:var(--fraco); font-size:.74rem;
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
 #lista { display:grid; gap:.55rem; padding-top:.15rem; padding-bottom:.8rem }
 #lista button { display:flex; justify-content:space-between; align-items:center;
        gap:.7rem; width:100%; text-align:left; padding:.65rem .85rem;
        color:var(--txt); background:var(--card); cursor:pointer;
        border:1px solid var(--borda); border-radius:14px;
        transition:border-color .15s;
        font:600 .95rem/1.3 "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif }
 #lista button:hover { border-color:#31405a }
 #lista button.sel { background:#1c3050; border-color:#3a5a8c }
 #lista button b { font-weight:650; font-size:.72rem; color:var(--mut);
        background:var(--card2); border:1px solid var(--linha);
        border-radius:999px; padding:.02rem .55rem .08rem;
        font-variant-numeric:tabular-nums; flex:none }
 #titulo, #tituloRes { font:650 1.05rem/1.3 "Segoe UI Variable Display",
           "Segoe UI", system-ui, sans-serif; margin:.45rem 0 .1rem }
 .agrupa { color:var(--fraco); font-size:.76rem; margin:0 0 .55rem }
 .tabela { background:var(--card); border:1px solid var(--borda);
           border-radius:14px; overflow:auto; margin:.55rem 0 1rem }
 table { width:100%; border-collapse:collapse; font-size:.89rem }
 th { text-align:left; color:var(--fraco); font-size:.72rem; font-weight:650;
      text-transform:uppercase; letter-spacing:.07em; padding:.45rem .65rem .4rem;
      border-bottom:1px solid var(--borda); position:sticky; top:0;
      background:var(--card); z-index:1; white-space:nowrap }
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
          font-weight:400; white-space:nowrap; background:#222835;
          color:var(--mut) }
 .minimo { font-weight:650 }
 th.mao { color:var(--mut) }
 td.mao { min-width:4rem }
 #barra { position:fixed; left:0; right:0; bottom:0; z-index:3;
          background:var(--card); border-top:1px solid var(--borda);
          padding:.6rem .85rem; display:none; gap:.55rem;
          justify-content:center }
 #barra button { font-size:.95rem; padding:.45rem 1.1rem }
 #dlg { position:fixed; inset:0; z-index:4; display:none;
        background:rgba(0,0,0,.55); align-items:center; justify-content:center }
 #dlg .caixa { background:var(--card); border:1px solid var(--borda);
        border-radius:14px; padding:1rem; width:min(28rem, 92vw) }
 #dlg h3 { font-size:1rem; margin-bottom:.6rem }
 #dlg .membros { color:var(--mut); font-size:.82rem; margin-bottom:.7rem;
        max-height:8rem; overflow:auto }
 #dlg input { width:100%; padding:.5rem .8rem; font-size:1rem;
        color:var(--txt); background:var(--card2);
        border:1px solid var(--borda); border-radius:10px; outline:none }
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
 footer { color:var(--fraco); font-size:.74rem; padding-bottom:1rem }
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
  <button id="btnAgrupar" title="juntar filiais do mesmo fornecedor">&#128279; agrupar filiais</button>
 </div>
 <div id="lista"></div>
</div>
<div id="detalhe" style="display:none">
 <div class="acoes nao-imprime">
  <button id="volta">&larr; fornecedores</button>
  <button id="pdf" title="imprimir / salvar em PDF">&#128424; salvar PDF</button>
  <button id="btnMae" title="juntar este fornecedor a outro">&#128279; definir m&atilde;e</button>
  <button id="btnMover" title="mandar itens para outro fornecedor">&#9745; mover itens</button>
 </div>
 <h2 id="titulo"></h2>
 <div class="agrupa" id="agrupaInfo"></div>
 <div class="soprint">dados de __DADOS_DE__ &middot; AtacadeRJ</div>
 <div class="tabela"><table><thead><tr id="cabDet">
 <th>c&oacute;digo</th><th>produto</th><th>corredor</th>
 <th class="num">cx m&atilde;e</th><th class="num">est. m&iacute;nimo</th>
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
 <div class="tabela"><table><thead><tr>
 <th>c&oacute;digo</th><th>produto</th><th>fornecedor</th><th>corredor</th>
 <th class="num">cx m&atilde;e</th><th class="num">est. m&iacute;nimo</th>
 </tr></thead><tbody id="corpoRes"></tbody></table></div>
</div>
<footer>&#9888;&#65039; = poss&iacute;vel ruptura AGORA (detector de estoque) &middot;
 * = calculado com ruptura (pode estar subestimado) &middot;
 novo = estimativa proporcional (produto recente) &middot;
 sem venda 6m / ruptura cr&ocirc;nica = sem base de venda (m&iacute;nimo = piso de 1 cx/un) &middot;
 cx m&atilde;e = unidades por caixa (1 = sem caixa)</footer>
</div>
<div id="barra"></div>
<div id="dlg"><div class="caixa">
 <h3 id="dlgTitulo"></h3>
 <div class="membros" id="dlgMembros"></div>
 <input id="dlgNome" list="dlForn" placeholder="nome do fornecedor...">
 <datalist id="dlForn"></datalist>
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
var abertoNome = null, modoForn = false, modoItem = false;
var selForn = {}, selItem = {};
var $ = function(id){return document.getElementById(id);};
function esc(s){var d=document.createElement('div');
  d.appendChild(document.createTextNode(String(s)));return d.innerHTML;}

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
  var dl=$('dlForn'); dl.innerHTML='';
  nomes.forEach(function(n){var o=document.createElement('option');
    o.value=n; dl.appendChild(o);});
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
function renderLista(filtro){
  var el=$('lista'); el.innerHTML='';
  DADOS.forEach(function(f){
    if(filtro && f.nome.toUpperCase().indexOf(filtro.toUpperCase())<0)return;
    var b=document.createElement('button');
    b.innerHTML=(modoForn?(selForn[f.nome]?'\\u2611 ':'\\u2610 '):'')+
                esc(f.nome)+' <b>'+f.qtd+'</b>';
    if(selForn[f.nome])b.className='sel';
    b.onclick=function(){
      if(modoForn){selForn[f.nome]=!selForn[f.nome];
        if(!selForn[f.nome])delete selForn[f.nome];
        renderLista(filtro); renderBarra();}
      else abrir(f.nome);};
    el.appendChild(b);});
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
  f.produtos.forEach(function(p){
    var tr=document.createElement('tr');
    var chk=modoItem?('<td class="chk nao-imprime">'+
      (selItem[p.codigo]?'\\u2611':'\\u2610')+'</td>'):'';
    tr.innerHTML=chk+'<td class="cod">'+esc(p.codigo)+'</td><td class="desc">'+
      celProduto(p)+'</td><td>'+esc(p.rua)+
      '</td><td class="num">'+esc(p.cx)+
      '</td><td class="num minimo">'+esc(p.minimo)+'</td>'+
      '<td class="mao"></td>'.repeat(4);
    if(modoItem){tr.className='selv'+(selItem[p.codigo]?' on':'');
      tr.onclick=function(){selItem[p.codigo]=!selItem[p.codigo];
        if(!selItem[p.codigo])delete selItem[p.codigo];
        abrir(nome); renderBarra();};}
    corpo.appendChild(tr);});
  var cab=$('cabDet');
  var temChk=cab.firstChild && cab.firstChild.className==='chk nao-imprime';
  if(modoItem && !temChk){var th=document.createElement('th');
    th.className='chk nao-imprime'; cab.insertBefore(th, cab.firstChild);}
  if(!modoItem && temChk){cab.removeChild(cab.firstChild);}
  mostra('det');
}
function renderResultados(q){
  var Q=q.toUpperCase(), achou=0, total=0;
  var corpoRes=$('corpoRes'); corpoRes.innerHTML='';
  DADOS.forEach(function(f){
    f.produtos.forEach(function(p){
      if(p.nome.toUpperCase().indexOf(Q)<0 &&
         String(p.codigo).indexOf(Q)<0)return;
      total++;
      if(achou>=MAX_RES)return;
      achou++;
      var tr=document.createElement('tr');
      tr.className='link';
      tr.title='abrir '+f.nome;
      tr.innerHTML='<td class="cod">'+esc(p.codigo)+'</td><td class="desc">'+
        celProduto(p)+'</td><td class="forn">'+esc(f.nome)+'</td><td>'+esc(p.rua)+
        '</td><td class="num">'+esc(p.cx)+
        '</td><td class="num minimo">'+esc(p.minimo)+'</td>';
      tr.onclick=function(){$('buscaProd').value=''; abrir(f.nome);};
      corpoRes.appendChild(tr);});
  });
  $('tituloRes').textContent='produto: "'+q+'" \\u2014 '+total+
    ' resultado'+(total===1?'':'s')+(total>achou?' (mostrando '+achou+')':'');
  mostra('res');
}

/* ---- barra de acao dos modos de selecao ---- */
function renderBarra(){
  var b=$('barra');
  if(modoForn){
    var n=Object.keys(selForn).length;
    b.innerHTML='<button id="bDef" class="pill">definir m\\u00e3e ('+n+')</button>'+
                '<button id="bCan" class="pill">cancelar</button>';
    b.style.display='flex';
    $('bDef').onclick=function(){if(n)dlgAbrir(Object.keys(selForn));};
    $('bCan').onclick=sairModos;
  } else if(modoItem){
    var m=Object.keys(selItem).length;
    b.innerHTML='<button id="bMov" class="pill">mover '+m+' item(ns) para...</button>'+
                '<button id="bCan" class="pill">cancelar</button>';
    b.style.display='flex';
    $('bMov').onclick=function(){if(m)dlgMover();};
    $('bCan').onclick=sairModos;
  } else b.style.display='none';
}
function sairModos(){modoForn=false;modoItem=false;selForn={};selItem={};
  renderBarra();
  $('btnAgrupar').className=''; $('btnMover').className='';
  if(abertoNome && $('detalhe').style.display!=='none')abrir(abertoNome);
  else {renderLista($('busca').value); mostra('lista');}}

/* ---- dialogo: agrupar / definir mae ---- */
var dlgModo='';
function dlgAbrir(nomes){
  dlgModo='grupo'; window._dlgNomes=nomes;
  $('dlgTitulo').textContent='Agrupar filiais \\u2014 quem \\u00e9 a m\\u00e3e?';
  $('dlgMembros').textContent='membros: '+nomes.join(' \\u00b7 ');
  var maior=nomes[0], q=0;
  DADOS.forEach(function(f){
    if(nomes.indexOf(f.nome)>=0 && f.qtd>q){q=f.qtd;maior=f.nome;}});
  $('dlgNome').value=maior;
  $('dlgDesagrupar').style.display='';
  $('dlg').style.display='flex';
}
function dlgMover(){
  dlgModo='itens';
  var m=Object.keys(selItem).length;
  $('dlgTitulo').textContent='Mover '+m+' item(ns) para qual fornecedor?';
  $('dlgMembros').textContent='c\\u00f3digos: '+Object.keys(selItem).join(', ');
  $('dlgNome').value='';
  $('dlgDesagrupar').style.display='none';
  $('dlg').style.display='flex';
  $('dlgNome').focus();
}
$('dlgCancelar').onclick=function(){$('dlg').style.display='none';};
$('dlgDesagrupar').onclick=function(){
  (window._dlgNomes||[]).forEach(function(n){delete OVR.grupos[n];});
  $('dlg').style.display='none';
  salvar(function(){aplicar();sairModos();});
};
$('dlgOk').onclick=function(){
  var alvo=$('dlgNome').value.trim();
  if(!alvo)return;
  if(dlgModo==='grupo'){
    var nomes=window._dlgNomes||[];
    nomes.forEach(function(n){
      if(n!==alvo)OVR.grupos[n]=alvo;});
    // quem apontava para um dos filhos passa a apontar para a mae
    Object.keys(OVR.grupos).forEach(function(k){
      if(nomes.indexOf(OVR.grupos[k])>=0 && OVR.grupos[k]!==alvo)
        OVR.grupos[k]=alvo;});
    delete OVR.grupos[alvo];             // mae nao pode ser filha
  } else {
    Object.keys(selItem).forEach(function(c){OVR.itens[c]=alvo;});
  }
  $('dlg').style.display='none';
  var alvoFinal=resolve(alvo);
  salvar(function(){aplicar();
    if(dlgModo==='itens'){modoItem=false;selItem={};renderBarra();
      $('btnMover').className='';abrir(abertoNome||alvoFinal);}
    else sairModos();});
};

/* ---- botoes fixos ---- */
$('btnAgrupar').onclick=function(){
  modoForn=!modoForn; selForn={};
  this.className=modoForn?'on':'';
  renderLista($('busca').value); renderBarra();};
$('btnMae').onclick=function(){
  if(abertoNome)dlgAbrir([abertoNome]);};
$('btnMover').onclick=function(){
  modoItem=!modoItem; selItem={};
  this.className=modoItem?'on':'';
  abrir(abertoNome); renderBarra();};
$('volta').onclick=function(){sairModos();mostra('lista');};
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
aplicar(); renderLista('');
fetch('/listagem/overrides').then(function(r){return r.json();})
 .then(function(j){ if(j && j.grupos){OVR=j; aplicar();
   renderLista($('busca').value);} })
 .catch(function(){});
</script></body></html>
"""
