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

    # DORSAL so tem historico a partir do primeiro dia que aparece no canal
    # (comecou em 2026-01-22; tbVendaPDV vai a 2023). Com --dias grande, todo
    # dia oficial ANTERIOR a esse inicio cai como "SO NO OFICIAL" -- mas isso
    # nao e um buraco do canal, e so o DORSAL nao existir ainda naquela data.
    # Nao pode virar reprovacao por dia nem encher a tabela: vira 1 linha-resumo.
    min_canal = min(por_dia_canal) if por_dia_canal else None

    print(f"{'dia':<12} {'VENDAS_CANAL':>14} {'tbVendaPDV':>14} {'dif':>10}")
    falhou = False
    dias_ok = set()
    pre_dorsal = 0
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
            if min_canal is not None and dia < min_canal:
                # fora do periodo do DORSAL: nao e falha, e nem entra na tabela
                pre_dorsal += 1
                continue
            b = por_dia_oficial[dia]
            falhou = True
            print(f"{dia:<12} {'-':>14} {b:>14.3f} {'-':>10}  "
                  f"<<< SO NO OFICIAL (canal perdeu o dia)")

    if pre_dorsal:
        print(f"\n({pre_dorsal} dias oficiais anteriores ao inicio do DORSAL — "
              f"fora da comparacao)")

    # vazio nao e prova: se nenhum dia teve veredito OK, a reconciliacao nao
    # provou NADA -- nunca pode sair [OK] por vacuidade (o exit code e o
    # contrato que libera a Fase 2).
    if not dias_ok:
        falhou = True

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
