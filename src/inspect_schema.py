# -*- coding: utf-8 -*-
"""Introspecao do banco (usuario viewer, SOMENTE LEITURA): lista tabelas e
colunas para a gente ACHAR as tabelas/colunas certas e preencher src/queries.py.
Nao escreve nada no banco.

Uso (na maquina que alcanca o MySQL, com config.local.json preenchido):
  python src/inspect_schema.py                 # todas as tabelas + colunas
  python src/inspect_schema.py preco custo      # so o que casar com esses termos
  python src/inspect_schema.py produto venda entrada pedido curva

Dica: rode com termos (preco, custo, curva, venda, entrada, pedido, forn) para
achar rapido as tabelas certas no meio de um ERP grande.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    termos = [t.lower() for t in sys.argv[1:]]
    cfg_path = os.path.join(RAIZ, "config.local.json")
    if not os.path.exists(cfg_path):
        raise SystemExit("[ERRO] Preencha config.local.json (secao db) primeiro.")
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    schema = cfg["db"]["database"]

    conn = db.conectar(cfg["db"])
    try:
        linhas = db.consultar(conn, f"""
            SELECT TABLE_NAME AS t, COLUMN_NAME AS c, DATA_TYPE AS dt
            FROM information_schema.columns
            WHERE TABLE_SCHEMA = '{schema}'
            ORDER BY TABLE_NAME, ORDINAL_POSITION
        """)
    finally:
        conn.close()

    tabela_atual = None
    mostrou = 0
    for r in linhas:
        t, c, dt = r["t"], r["c"], r["dt"]
        if termos and not any(x in t.lower() or x in c.lower() for x in termos):
            continue
        if t != tabela_atual:
            print(f"\n== {t} ==")
            tabela_atual = t
        print(f"   {c}  ({dt})")
        mostrou += 1

    filtro = f"  (filtro: {termos})" if termos else ""
    print(f"\n[{mostrou} colunas]{filtro}")


if __name__ == "__main__":
    main()
