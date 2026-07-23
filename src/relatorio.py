# -*- coding: utf-8 -*-
"""HTML unico da listagem: dados embutidos + JS inline (sem rede).

Identidade visual = a MESMA do Painel de Compras (erp-bridge
src/templates/painel_compras.html: escuro operacional, Segoe UI Variable,
th maiusculas, zebra, numeros tabulares) — pedido do dono, 22/07. Se o
painel mudar de cara, atualizar as variaveis :root daqui junto.

Dono, 22/07 (mesma leva): coluna curva SAIU da tela (segue alimentando o
limiar de ruptura no calculo); botao "salvar PDF" (window.print() +
@media print — o navegador salva como PDF, offline); busca por PRODUTO ao
lado da busca de fornecedor (varre todos; toque abre o fornecedor);
coluna "cx mae" (unidades por caixa-mae; sem caixa = 1); conteudo num
container central (.miolo) — em tela larga o numero nao foge do cabecalho.

ARMADILHA conhecida (memoria do projeto): visualizador do WhatsApp nao
executa JavaScript — este arquivo e para abrir no NAVEGADOR."""
import html as _html
import json

import formato

COTACAO = "COTACAO"
SEM_FORNECEDOR = "SEM FORNECEDOR"
MARCAS_TXT = {"*": "*", "novo": "novo", "sem_venda": "sem venda 6m"}
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


def montar(fornecedores, dados_de):
    dados = [{"nome": f["nome"], "qtd": f["qtd"],
              "produtos": [{"codigo": p["codigo"],
                            "nome": p["nome"],
                            "rua": p.get("rua_rotulo") or "",
                            # unidades por caixa-mae; sem caixa = 1 (dono)
                            "cx": p.get("cx_mae") or 1,
                            "minimo": p["minimo"],
                            "marca": MARCAS_TXT.get(p.get("marca") or "", ""),
                            # alerta do detector de estoque (dono, 22/07):
                            # item presente no corte da ultima rodada
                            "rp": 1 if p.get("ruptura") else 0}
                           for p in f["produtos"]]}
             for f in fornecedores]
    # todo '<' do JSON vira a sequencia backslash-u003c: nenhum
    # "</script>" nem tag alguma consegue escapar do blob embutido
    blob = json.dumps(dados, ensure_ascii=False).replace("<", "\\u003c")
    return _TEMPLATE.replace("__DADOS__", blob) \
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
 body { background:var(--bg); color:var(--txt);
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
 #lista { display:grid; gap:.55rem; padding-top:.8rem; padding-bottom:.8rem }
 #lista button { display:flex; justify-content:space-between; align-items:center;
        gap:.7rem; width:100%; text-align:left; padding:.65rem .85rem;
        color:var(--txt); background:var(--card); cursor:pointer;
        border:1px solid var(--borda); border-radius:14px;
        transition:border-color .15s;
        font:600 .95rem/1.3 "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif }
 #lista button:hover { border-color:#31405a }
 #lista button b { font-weight:650; font-size:.72rem; color:var(--mut);
        background:var(--card2); border:1px solid var(--linha);
        border-radius:999px; padding:.02rem .55rem .08rem;
        font-variant-numeric:tabular-nums; flex:none }
 .acoes { display:flex; gap:.55rem; margin:.8rem 0 .2rem }
 .acoes button { padding:.3rem .9rem; font-size:.85rem;
          color:var(--mut); background:var(--card2);
          border:1px solid var(--borda); border-radius:999px; cursor:pointer }
 .acoes button:hover { border-color:#3a5a8c; color:var(--txt) }
 #pdf, #pdfRes { color:var(--acc) }
 #titulo, #tituloRes { font:650 1.05rem/1.3 "Segoe UI Variable Display",
           "Segoe UI", system-ui, sans-serif; margin:.45rem 0 .55rem }
 .tabela { background:var(--card); border:1px solid var(--borda);
           border-radius:14px; overflow:auto; margin-bottom:1rem }
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
 tr.link { cursor:pointer }
 .cod { color:var(--mut); font-variant-numeric:tabular-nums }
 .forn { color:var(--mut); font-size:.82rem }
 .marca { border-radius:999px; padding:.08rem .55rem .12rem; font-size:.76rem;
          font-weight:400; white-space:nowrap; background:#222835;
          color:var(--mut) }
 .minimo { font-weight:650 }
 /* 4 colunas de data p/ preencher A MAO (dono, 22/07): celula VAZIA,
    sem traco (pedido do dono); largura minima p/ caber caneta */
 th.mao { color:var(--mut) }
 td.mao { min-width:4rem }
 .soprint { display:none }
 footer { color:var(--fraco); font-size:.74rem; padding-bottom:1rem }
 @media print {
   body { background:#fff; color:#000;
          font:12px/1.35 "Segoe UI", system-ui, sans-serif }
   header, footer, .acoes, #lista { display:none !important }
   .miolo { max-width:none; padding:0 }
   .soprint { display:block; color:#333; font-size:11px; margin:0 0 6px }
   #titulo, #tituloRes { color:#000; margin:6px 0 }
   .tabela { border:none; border-radius:0; overflow:visible }
   th { position:static; background:#fff !important; color:#000;
        border-bottom:1px solid #999 }
   td { background:#fff !important; color:#000; border-color:#ccc }
   td.cod, .forn { color:#333 }
   tr:nth-child(even) td { background:#f3f3f3 !important }
   /* PDF limpo (dono, 22/07): sem emoji de ruptura nem etiquetas de aviso
      — o papel vai para o fornecedor, os avisos sao internos */
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
<div id="lista"></div>
<div id="detalhe" style="display:none">
 <div class="acoes">
  <button id="volta">&larr; fornecedores</button>
  <button id="pdf" title="imprimir / salvar em PDF">&#128424; salvar PDF</button>
 </div>
 <h2 id="titulo"></h2>
 <div class="soprint">dados de __DADOS_DE__ &middot; AtacadeRJ</div>
 <div class="tabela"><table><thead><tr>
 <th>c&oacute;digo</th><th>produto</th><th>corredor</th>
 <th class="num">cx m&atilde;e</th><th class="num">est. m&iacute;nimo</th>
 <th class="mao">data __/__/__</th><th class="mao">data __/__/__</th>
 <th class="mao">data __/__/__</th><th class="mao">data __/__/__</th>
 </tr></thead><tbody id="corpo"></tbody></table></div>
</div>
<div id="resultados" style="display:none">
 <div class="acoes">
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
 sem venda 6m = nenhuma venda no hist&oacute;rico &middot;
 cx m&atilde;e = unidades por caixa (1 = sem caixa)</footer>
</div>
<script>
var DADOS = __DADOS__, MAX_RES = __MAX_RES__;
var lista = document.getElementById('lista'),
    det = document.getElementById('detalhe'),
    res = document.getElementById('resultados'),
    corpo = document.getElementById('corpo'),
    corpoRes = document.getElementById('corpoRes');
function esc(s){var d=document.createElement('div');
  d.appendChild(document.createTextNode(String(s)));return d.innerHTML;}
function mostra(alvo){ /* uma vista por vez */
  lista.style.display = (alvo==='lista') ? 'grid' : 'none';
  det.style.display   = (alvo==='det')   ? 'block' : 'none';
  res.style.display   = (alvo==='res')   ? 'block' : 'none';
}
function celProduto(p){
  return (p.rp?'<span class="rupt" title="possível ruptura">⚠️</span> ':'')+
         esc(p.nome)+
         (p.marca?' <span class="marca">'+esc(p.marca)+'</span>':'');
}
function renderLista(filtro){
  lista.innerHTML='';
  DADOS.forEach(function(f,i){
    if(filtro && f.nome.toUpperCase().indexOf(filtro.toUpperCase())<0)return;
    var b=document.createElement('button');
    b.innerHTML=esc(f.nome)+' <b>'+f.qtd+'</b>';
    b.onclick=function(){abrir(i);};
    lista.appendChild(b);});
}
function abrir(i){
  var f=DADOS[i];
  document.getElementById('titulo').textContent=f.nome+' — '+f.qtd+' produtos';
  corpo.innerHTML='';
  f.produtos.forEach(function(p){
    var tr=document.createElement('tr');
    tr.innerHTML='<td class="cod">'+esc(p.codigo)+'</td><td class="desc">'+
      celProduto(p)+'</td><td>'+esc(p.rua)+
      '</td><td class="num">'+esc(p.cx)+
      '</td><td class="num minimo">'+esc(p.minimo)+'</td>'+
      '<td class="mao"></td>'.repeat(4);
    corpo.appendChild(tr);});
  mostra('det');
  window.scrollTo(0,0);
}
function renderResultados(q){
  var Q=q.toUpperCase(), achou=0, total=0;
  corpoRes.innerHTML='';
  DADOS.forEach(function(f,i){
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
      tr.onclick=function(){abrir(i);};
      corpoRes.appendChild(tr);});
  });
  document.getElementById('tituloRes').textContent =
    'produto: "'+q+'" — '+total+' resultado'+(total===1?'':'s')+
    (total>achou?' (mostrando '+achou+')':'');
  mostra('res');
}
document.getElementById('volta').onclick=function(){mostra('lista');};
document.getElementById('voltaRes').onclick=function(){
  document.getElementById('buscaProd').value='';mostra('lista');};
document.getElementById('pdf').onclick=function(){window.print();};
document.getElementById('pdfRes').onclick=function(){window.print();};
document.getElementById('busca').oninput=function(){
  document.getElementById('buscaProd').value='';
  mostra('lista');renderLista(this.value);};
document.getElementById('buscaProd').oninput=function(){
  var q=this.value.trim();
  if(q.length>=2){renderResultados(q);}
  else{mostra('lista');renderLista(document.getElementById('busca').value);}
};
renderLista('');
</script></body></html>
"""
