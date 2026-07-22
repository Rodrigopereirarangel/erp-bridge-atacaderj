# -*- coding: utf-8 -*-
"""Ad-hoc (22/07): por que o 38331 (ACUCAR ORGANICO GUARANI) ainda aparece
sem prateleira? Mostra o cadastro CRU: no da classificacao apontado, cadeia
com codigos/empresas, filhos do CORREDOR 100 (FOOD) e alteracoes recentes."""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
import db  # noqa: E402

COD = 38331


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    cfg = json.load(open(os.path.join(RAIZ, "config.local.json"), encoding="utf-8"))
    conn = db.conectar(cfg["db"])
    try:
        base = db.consultar(conn, f"""
            SELECT p.cdProduto, p.cdSuperProduto, sp.cdEmpresa,
                   sp.cdClassificacaoProduto, sp.nmProdutoPai
            FROM dbo.tbProduto p
            JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = p.cdSuperProduto
            WHERE p.cdProduto = {COD}""")
        for r in base:
            print("produto:", r)
        no = base[0]["cdClassificacaoProduto"]
        emp = base[0]["cdEmpresa"]
        print("\ncadeia a partir do no apontado:")
        nivel = 0
        while no is not None and nivel < 6:
            linha = db.consultar(conn, f"""
                SELECT cdClassificacaoProduto, cdEmpresa,
                       nmClassificacaoProduto, cdClassificacaoProdutoPai,
                       cdEmpresaPai
                FROM dbo.tbClassificacaoProduto
                WHERE cdClassificacaoProduto = {no} AND cdEmpresa = {emp}""")
            if not linha:
                print(f"  nivel {nivel}: NO {no}/emp {emp} NAO EXISTE na tabela!")
                break
            l = linha[0]
            print(f"  nivel {nivel}: [{l['cdClassificacaoProduto']}/emp "
                  f"{l['cdEmpresa']}] {l['nmClassificacaoProduto']!r}")
            no, emp = l["cdClassificacaoProdutoPai"], l["cdEmpresaPai"]
            nivel += 1

        print("\nfilhos de cada no com 'CORREDOR 100' no nome:")
        for pai in db.consultar(conn, """
                SELECT cdClassificacaoProduto, cdEmpresa, nmClassificacaoProduto
                FROM dbo.tbClassificacaoProduto
                WHERE nmClassificacaoProduto LIKE '%CORREDOR 100%'"""):
            print(f"  pai [{pai['cdClassificacaoProduto']}/emp {pai['cdEmpresa']}]"
                  f" {pai['nmClassificacaoProduto']!r}")
            for f_ in db.consultar(conn, f"""
                    SELECT cdClassificacaoProduto, cdEmpresa, nmClassificacaoProduto
                    FROM dbo.tbClassificacaoProduto
                    WHERE cdClassificacaoProdutoPai = {pai['cdClassificacaoProduto']}
                      AND cdEmpresaPai = {pai['cdEmpresa']}"""):
                print(f"     filho [{f_['cdClassificacaoProduto']}/emp "
                      f"{f_['cdEmpresa']}] {f_['nmClassificacaoProduto']!r}")

        print("\ncolunas de data/auditoria em tbSuperProduto:")
        for c in db.consultar(conn, """
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'tbSuperProduto'
                  AND (COLUMN_NAME LIKE '%dt%' OR COLUMN_NAME LIKE '%Alter%')"""):
            print("  ", c["COLUMN_NAME"])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
