# -*- coding: utf-8 -*-
"""PROVA de que VENDAS_CANAL esta correta: a soma das unidades por dia tem
que bater EXATO com Solidcon.tbVendaPDV (a base oficial, ja validada contra
o consolidado do PDV em DORSAL.tbConsVenda).

Se nao bater, a causa quase certa e a resolucao de EAN (tbProdutoVenda):
o cupom traz ora codigo interno, ora EAN, e cada EAN tem multiplicador.

Uso (NO PC-PONTE — a dev nao alcanca o banco):
  python scripts/verificar-reconciliacao-canal.py
  python scripts/verificar-reconciliacao-canal.py --dias 7
"""
import argparse
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
import db       # noqa: E402
import queries  # noqa: E402

TOLERANCIA = 0.001  # unidades: tem que bater ao decimal, nao "mais ou menos"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=3, help="dias a conferir (default 3)")
    ap.add_argument("--config", default=os.path.join(RAIZ, "config.local.json"))
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    pdvs = cfg.get("exposicao", {}).get("pdvs_atacado", [11, 12])
    conn = db.conectar(cfg["db"])
    try:
        canal = db.consultar(conn, queries.VENDAS_CANAL.format(
            janela_exposicao=args.dias,
            pdvs_atacado=", ".join(str(int(p)) for p in pdvs)))
        oficial = db.consultar(conn, f"""
            SELECT CAST(v.dtVenda AS date) AS data,
                   CAST(SUM(v.qtVenda) AS decimal(14,3)) AS unidades
            FROM dbo.tbVendaPDV v
            WHERE v.dtVenda >= DATEADD(day, -{int(args.dias)}, CAST(GETDATE() AS date))
              AND v.cdProduto IS NOT NULL
            GROUP BY CAST(v.dtVenda AS date)
            ORDER BY data
        """)
    finally:
        conn.close()

    por_dia = {}
    for r in canal:
        por_dia[str(r["data"])] = por_dia.get(str(r["data"]), 0.0) + float(r["unidades"])

    print(f"{'dia':<12} {'VENDAS_CANAL':>14} {'tbVendaPDV':>14} {'dif':>10}")
    falhou = False
    for r in oficial:
        dia = str(r["data"])
        a, b = por_dia.get(dia, 0.0), float(r["unidades"])
        dif = a - b
        marca = "OK" if abs(dif) <= TOLERANCIA else "<<< NAO BATE"
        if abs(dif) > TOLERANCIA:
            falhou = True
        print(f"{dia:<12} {a:>14.3f} {b:>14.3f} {dif:>10.3f}  {marca}")

    # o motivo de tudo isto existir: quanto o atacado distorceria o giro
    salao = sum(float(r["unidades"]) for r in canal if r["canal"] == "salao")
    atacado = sum(float(r["unidades"]) for r in canal if r["canal"] == "atacado")
    print(f"\nsalao   : {salao:12.1f} un")
    print(f"atacado : {atacado:12.1f} un  ({atacado / (salao + atacado) * 100:.1f}% do volume)")
    if salao:
        print(f"incluir o atacado inflaria o giro em {atacado / salao * 100:.0f}%")

    if falhou:
        print("\n[FALHOU] A resolucao de EAN esta errada. NAO use esta base.", file=sys.stderr)
        sys.exit(1)
    print("\n[OK] Reconciliacao exata: a base esta correta.")


if __name__ == "__main__":
    main()
