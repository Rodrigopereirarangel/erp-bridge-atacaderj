# -*- coding: utf-8 -*-
"""Conexao SOMENTE-LEITURA com o banco do ERP.

Dialetos (config db.tipo): "sqlserver" (pyodbc) e "mysql" (pymysql).
O AtacadeRJ usa **SQL Server 2014** (banco Solidcon, porta 1433) — descoberto
na implantacao de 2026-07-07; o projeto nasceu assumindo MySQL, dai o modo duplo.

Guarda de seguranca: so executa SELECT/WITH. Se alguma query mudar para algo
que escreve, a funcao levanta erro em vez de rodar. O usuario do banco ja e
somente leitura; isto e uma segunda trava, do lado do codigo.
"""

import decimal


def conectar(db_cfg):
    cfg = dict(db_cfg)
    tipo = cfg.pop("tipo", "mysql").lower()
    if tipo == "sqlserver":
        import pyodbc
        cs = ("DRIVER={%s};SERVER=%s,%s;DATABASE=%s;UID=%s;PWD=%s" % (
            cfg.get("driver", "SQL Server"), cfg["host"], cfg.get("port", 1433),
            cfg["database"], cfg["user"], cfg["password"]))
        return pyodbc.connect(cs, timeout=int(cfg.get("connect_timeout", 15)))
    import pymysql
    cfg.pop("driver", None)
    return pymysql.connect(**cfg)


def _e_somente_leitura(sql):
    inicio = sql.lstrip().lstrip("(").lstrip().upper()
    return inicio.startswith("SELECT") or inicio.startswith("WITH")


def _valor(v):
    # money/decimal do SQL Server viram float (produtos.json precisa de numero, nao string)
    if isinstance(v, decimal.Decimal):
        return round(float(v), 6)
    return v


def consultar(conn, sql):
    """Roda um SELECT e devolve lista de dicts (uma linha = um dict)."""
    if not _e_somente_leitura(sql):
        raise ValueError("Bloqueado: esta ponte so executa SELECT (usuario somente-leitura).")
    cur = conn.cursor()
    try:
        cur.execute(sql)
        colunas = [d[0] for d in cur.description]
        return [dict(zip(colunas, map(_valor, linha))) for linha in cur.fetchall()]
    finally:
        cur.close()
