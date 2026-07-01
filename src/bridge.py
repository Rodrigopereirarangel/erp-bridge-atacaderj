# -*- coding: utf-8 -*-
"""Ponte ERP -> arquivos dos consumidores (AtacadeRJ).

Extrai (SELECT, usuario viewer) catalogo/vendas/recebimentos/pedidos e escreve,
via camada de projecao, o formato exato de cada consumidor:

  catalogo     -> cotacao/produtos.json  +  detector-estoque/curva_abc.csv
  vendas       -> detector-salao/vendas.csv        (sem valor)
                  detector-estoque/vendas.csv       (com valor R$)
  recebimentos -> detector-salao/recebimentos.csv  +  detector-estoque/recebimentos.csv
  pedidos      -> detector-estoque/pedidos.csv

Uso:
  python src/bridge.py --demo                # gera tudo com dados falsos (sem banco)
  python src/bridge.py                       # gera tudo lendo o MySQL (config.local.json)
  python src/bridge.py --only catalogo       # so o catalogo (para o agendamento 3-5x/dia)
  python src/bridge.py --only movimentos     # vendas+recebimentos+pedidos (agendamento diario)
  python src/bridge.py --config caminho.json # usa outro arquivo de config
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projections  # noqa: E402
import queries      # noqa: E402
import demo_data    # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def carregar_config(caminho):
    if caminho is None:
        caminho = os.path.join(RAIZ, "config.local.json")
    if not os.path.exists(caminho):
        raise SystemExit(
            f"[ERRO] Config nao encontrada: {caminho}\n"
            f"       Copie config.example.json para config.local.json e preencha "
            f"(ou rode com --demo)."
        )
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def coletar(cfg, usar_demo):
    """Devolve as 4 tabelas brutas, do banco ou do demo."""
    janela = cfg.get("janela_dias", 120)
    if usar_demo:
        return (demo_data.catalogo(), demo_data.vendas(janela),
                demo_data.recebimentos(), demo_data.pedidos())

    import db
    conn = db.conectar(cfg["db"])
    try:
        cat = db.consultar(conn, queries.CATALOGO)
        ven = db.consultar(conn, queries.VENDAS.format(janela=int(janela)))
        rec = db.consultar(conn, queries.RECEBIMENTOS.format(janela=int(janela)))
        ped = db.consultar(conn, queries.PEDIDOS)
    finally:
        conn.close()
    return cat, ven, rec, ped


def escrever(cfg, cat, ven, rec, ped, alvo):
    saida = cfg["saida"]
    salao = saida["detector_salao_dir"]
    estoque = saida["detector_estoque_dir"]
    gerado_em = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rel = []

    if alvo in ("all", "catalogo"):
        n = projections.cotacao_produtos_json(cat, saida["cotacao_produtos_json"], gerado_em)
        rel.append(f"cotacao/produtos.json: {n}")
        n = projections.curva_abc_csv(cat, os.path.join(estoque, "curva_abc.csv"))
        rel.append(f"detector-estoque/curva_abc.csv: {n}")

    if alvo in ("all", "movimentos", "vendas"):
        n = projections.vendas_csv(ven, os.path.join(salao, "vendas.csv"), incluir_valor=False)
        rel.append(f"detector-salao/vendas.csv: {n}")
        n = projections.vendas_csv(ven, os.path.join(estoque, "vendas.csv"), incluir_valor=True)
        rel.append(f"detector-estoque/vendas.csv: {n}")

    if alvo in ("all", "movimentos", "recebimentos"):
        n = projections.recebimentos_csv(rec, os.path.join(salao, "recebimentos.csv"))
        rel.append(f"detector-salao/recebimentos.csv: {n}")
        n = projections.recebimentos_csv(rec, os.path.join(estoque, "recebimentos.csv"))
        rel.append(f"detector-estoque/recebimentos.csv: {n}")

    if alvo in ("all", "movimentos", "pedidos"):
        n = projections.pedidos_csv(ped, os.path.join(estoque, "pedidos.csv"))
        rel.append(f"detector-estoque/pedidos.csv: {n}")

    return rel


def main():
    ap = argparse.ArgumentParser(description="Ponte ERP -> consumidores AtacadeRJ")
    ap.add_argument("--demo", action="store_true", help="usa dados falsos, sem tocar no banco")
    ap.add_argument("--only", default="all",
                    choices=["all", "catalogo", "movimentos", "vendas", "recebimentos", "pedidos"],
                    help="qual bloco gerar (default: all)")
    ap.add_argument("--config", default=None, help="caminho do config (default: config.local.json)")
    args = ap.parse_args()

    inicio = datetime.now()
    try:
        cfg = (json.load(open(os.path.join(RAIZ, "config.example.json"), encoding="utf-8"))
               if args.demo else carregar_config(args.config))
        cat, ven, rec, ped = coletar(cfg, args.demo)
        relatorio = escrever(cfg, cat, ven, rec, ped, args.only)
    except Exception as e:  # loga ao lado, util quando roda pelo Agendador
        with open(os.path.join(RAIZ, "bridge_erros.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  ERRO: {e}\n")
        print(f"[ERRO] {e}", file=sys.stderr)
        sys.exit(1)

    dur = (datetime.now() - inicio).total_seconds()
    print(f"[OK] ({'demo' if args.demo else 'banco'}) escrito em {dur:.1f}s:")
    for linha in relatorio:
        print(f"     - {linha}")


if __name__ == "__main__":
    main()
