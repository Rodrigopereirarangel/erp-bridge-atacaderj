# -*- coding: utf-8 -*-
"""Le os 4 CSVs do bridge + estado de ruas do deposito e escreve o HTML.

Manual por enquanto (decisao do dono 22/07: SEM tarefa agendada ate ele
validar os numeros). Falha de insumo -> exit 1 e o HTML anterior fica."""
import argparse
import csv
import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formato      # noqa: E402
import fornecedor   # noqa: E402
import minimo       # noqa: E402
import relatorio    # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ler_csv(caminho):
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def _ler_ruas(caminho):
    """Estado do deposito: {"15450": {"rua": 13, ...}} ou {"15450": 13}."""
    if not caminho or not os.path.exists(caminho):
        return {}
    with open(caminho, encoding="utf-8") as f:
        bruto = json.load(f)
    ruas = {}
    for cod, v in bruto.items():
        rua = v.get("rua") if isinstance(v, dict) else v
        if isinstance(rua, int):
            ruas[int(cod)] = rua
    return ruas


def main():
    ap = argparse.ArgumentParser(description="Listagem por fornecedor (HTML)")
    ap.add_argument("--config", default=os.path.join(RAIZ, "config.local.json"))
    args = ap.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    ent = cfg["entrada"]

    cat = _ler_csv(ent["catalogo_csv"])
    vendas_rows = _ler_csv(ent["vendas_csv"])
    entradas = [{"codigo": int(r["codigo"]), "data": r["data"],
                 "fornecedor": r["fornecedor"], "qtd": float(r["qtd"])}
                for r in _ler_csv(ent["entradas_csv"])]
    negociacoes = [{"codigo": int(r["codigo"]), "fornecedor": r["fornecedor"],
                    "dt_alteracao": r["dt_alteracao"]}
                   for r in _ler_csv(ent["negociacao_csv"])]
    ruas = _ler_ruas(ent.get("ruas_estado_json"))

    vendas_por_cod = {}
    datas = []
    for r in vendas_rows:
        cod = int(r["codigo"])
        vendas_por_cod.setdefault(cod, {})[r["data"]] = \
            vendas_por_cod.get(cod, {}).get(r["data"], 0.0) + float(r["qtd_vendida"])
        datas.append(r["data"])
    fim = date.fromisoformat(max(datas)) if datas else date.today()

    mapa_forn = fornecedor.atribuir(negociacoes, entradas)

    por_fornecedor = {}
    for p in cat:
        if str(p.get("ativo")) != "1":
            continue
        cod = int(p["codigo"])
        unidades, marca = minimo.calcular(
            vendas_por_cod.get(cod, {}), fim, p.get("curva") or None)
        embalagem = float(p["embalagem"]) if p.get("embalagem") else None
        peso = str(p.get("peso")) == "1"
        rua = ruas.get(cod)
        linha = {"codigo": cod, "nome": p["descricao"],
                 "curva": p.get("curva") or "", "rua": rua,
                 "rua_rotulo": formato.rotulo_rua(rua),
                 "minimo": formato.exibir(unidades, embalagem, peso),
                 "marca": marca}
        nome_forn = mapa_forn.get(cod, fornecedor.SEM_FORNECEDOR)
        por_fornecedor.setdefault(nome_forn, []).append(linha)

    dados_de = datetime.fromtimestamp(
        os.path.getmtime(ent["vendas_csv"])).strftime("%d/%m/%Y %H:%M")
    html = relatorio.montar(relatorio.preparar(por_fornecedor), dados_de)

    destino = cfg["saida_html"]
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    tmp = destino + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, destino)
    print(f"OK: {destino} ({sum(len(v) for v in por_fornecedor.values())} "
          f"produtos, {len(por_fornecedor)} fornecedores, dados de {dados_de})")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:                      # noqa: BLE001
        print(f"[ERRO] listagem NAO gerada (a anterior fica): {e}",
              file=sys.stderr)
        sys.exit(1)
