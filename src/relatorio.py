# -*- coding: utf-8 -*-
"""HTML unico da listagem: dados embutidos + JS inline (sem rede).

ARMADILHA conhecida (memoria do projeto): visualizador do WhatsApp nao
executa JavaScript — este arquivo e para abrir no NAVEGADOR."""
import html as _html
import json

import formato

COTACAO = "COTACAO"
SEM_FORNECEDOR = "SEM FORNECEDOR"
MARCAS_TXT = {"*": "*", "novo": "novo", "sem_venda": "sem venda 6m"}


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
                            "curva": p.get("curva") or "",
                            "rua": p.get("rua_rotulo") or "",
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
                    .replace("__DADOS_DE__", _html.escape(dados_de))


_TEMPLATE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Listagem por fornecedor</title>
<style>
 body{font-family:system-ui,Arial,sans-serif;margin:0;background:#f5f5f2;color:#222}
 header{position:sticky;top:0;background:#1a3c34;color:#fff;padding:10px 12px}
 header h1{font-size:16px;margin:0 0 6px}
 header small{opacity:.8}
 #busca{width:100%;box-sizing:border-box;padding:10px;font-size:16px;
        border:none;border-radius:6px;margin-top:6px}
 #lista button{display:block;width:100%;text-align:left;padding:12px;
        font-size:15px;border:none;border-bottom:1px solid #ddd;
        background:#fff;cursor:pointer}
 #lista button b{float:right;color:#666;font-weight:normal}
 #volta{margin:8px 12px;padding:8px 14px;font-size:14px}
 table{border-collapse:collapse;width:100%;background:#fff}
 th,td{padding:8px 10px;border-bottom:1px solid #e5e5e5;font-size:14px;
       text-align:left;vertical-align:top}
 th{background:#eee;position:sticky;top:0}
 td.num{text-align:right;white-space:nowrap}
 .marca{color:#b3541e;font-size:12px}
 footer{padding:10px 12px;color:#666;font-size:12px}
</style></head><body>
<header><h1>Listagem por fornecedor</h1>
<small>dados de __DADOS_DE__</small>
<input id="busca" type="search" placeholder="buscar fornecedor...">
</header>
<div id="lista"></div>
<div id="detalhe" style="display:none">
 <button id="volta">&larr; fornecedores</button>
 <h2 id="titulo" style="margin:4px 12px;font-size:16px"></h2>
 <table><thead><tr><th>c&oacute;digo</th><th>produto</th><th>curva</th>
 <th>corredor</th><th>est. m&iacute;nimo</th></tr></thead>
 <tbody id="corpo"></tbody></table>
</div>
<footer>&#9888;&#65039; = poss&iacute;vel ruptura AGORA (detector de estoque) &middot;
 * = calculado com ruptura (pode estar subestimado) &middot;
 novo = estimativa proporcional (produto recente) &middot;
 sem venda 6m = nenhuma venda no hist&oacute;rico</footer>
<script>
var DADOS = __DADOS__;
var lista = document.getElementById('lista'),
    det = document.getElementById('detalhe'),
    corpo = document.getElementById('corpo');
function esc(s){var d=document.createElement('div');
  d.appendChild(document.createTextNode(String(s)));return d.innerHTML;}
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
    tr.innerHTML='<td>'+esc(p.codigo)+'</td><td>'+
      (p.rp?'<span title="possível ruptura">⚠️</span> ':'')+esc(p.nome)+
      (p.marca?' <span class="marca">'+esc(p.marca)+'</span>':'')+
      '</td><td>'+esc(p.curva)+'</td><td>'+esc(p.rua)+
      '</td><td class="num">'+esc(p.minimo)+'</td>';
    corpo.appendChild(tr);});
  lista.style.display='none';det.style.display='block';
  window.scrollTo(0,0);
}
document.getElementById('volta').onclick=function(){
  det.style.display='none';lista.style.display='block';};
document.getElementById('busca').oninput=function(){renderLista(this.value);};
renderLista('');
</script></body></html>
"""
