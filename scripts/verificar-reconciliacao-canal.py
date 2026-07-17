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
        # relogio do BANCO, nao o local -- e o que decide se um dia "so no
        # canal" e o dia corrente (ainda sem consolidado) ou um buraco real
        hoje = str(db.consultar(conn, "SELECT CAST(GETDATE() AS date) AS hoje")[0]["hoje"])
    finally:
        conn.close()

    por_dia_canal = {}
    for r in canal:
        dia = str(r["data"])
        por_dia_canal[dia] = por_dia_canal.get(dia, 0.0) + float(r["unidades"])

    por_dia_oficial = {str(r["data"]): float(r["unidades"]) for r in oficial}

    # UNIAO das datas dos dois lados: um dia so em um dos lados nao pode
    # simplesmente sumir da tabela (era o bug -- a data corrente do DORSAL,
    # ou qualquer dia historico ausente do oficial, ficava de fora e o
    # falhou nunca disparava)
    dias = sorted(set(por_dia_canal) | set(por_dia_oficial))

    print(f"{'dia':<12} {'VENDAS_CANAL':>14} {'tbVendaPDV':>14} {'dif':>10}")
    falhou = False
    dias_ok = set()
    for dia in dias:
        em_canal = dia in por_dia_canal
        em_oficial = dia in por_dia_oficial
        if em_canal and em_oficial:
            a, b = por_dia_canal[dia], por_dia_oficial[dia]
            dif = a - b
            if abs(dif) > TOLERANCIA:
                falhou = True
                marca = "<<< NAO BATE"
            else:
                dias_ok.add(dia)
                marca = "OK"
            print(f"{dia:<12} {a:>14.3f} {b:>14.3f} {dif:>10.3f}  {marca}")
        elif em_canal:
            a = por_dia_canal[dia]
            if dia == hoje:
                print(f"{dia:<12} {a:>14.3f} {'-':>14} {'-':>10}  "
                      f"(dia corrente, sem consolidado oficial — fora da prova e do resumo)")
            else:
                falhou = True
                print(f"{dia:<12} {a:>14.3f} {'-':>14} {'-':>10}  "
                      f"<<< SO NO DORSAL (faltou consolidado oficial)")
        else:  # em_oficial apenas
            b = por_dia_oficial[dia]
            falhou = True
            print(f"{dia:<12} {'-':>14} {b:>14.3f} {'-':>10}  "
                  f"<<< SO NO OFICIAL (canal perdeu o dia)")

    # o motivo de tudo isto existir: quanto o atacado distorceria o giro --
    # so sobre dias com veredito OK (exclui o dia corrente parcial e
    # qualquer dia que tenha falhado a prova)
    salao = sum(float(r["unidades"]) for r in canal
                if r["canal"] == "salao" and str(r["data"]) in dias_ok)
    atacado = sum(float(r["unidades"]) for r in canal
                  if r["canal"] == "atacado" and str(r["data"]) in dias_ok)
    total = salao + atacado
    print(f"\nsalao   : {salao:15.3f} un")
    if total:
        print(f"atacado : {atacado:15.3f} un  ({atacado / total * 100:.3f}% do volume)")
    else:
        print(f"atacado : {atacado:15.3f} un  (sem dias com veredito OK no periodo)")
    if salao:
        print(f"incluir o atacado inflaria o giro em {atacado / salao * 100:.3f}%")

    if falhou:
        print("\n[FALHOU] A resolucao de EAN esta errada. NAO use esta base.", file=sys.stderr)
        sys.exit(1)
    print("\n[OK] Reconciliacao exata: a base esta correta.")


if __name__ == "__main__":
    main()
