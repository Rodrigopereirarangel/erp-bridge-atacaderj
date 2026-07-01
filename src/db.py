# -*- coding: utf-8 -*-
"""Conexao com o MySQL usando o usuario `viewer` (somente leitura).

Guarda de seguranca: so executa SELECT/WITH. Se alguma query mudar para algo
que escreve, a funcao levanta erro em vez de rodar. O usuario `viewer` ja e
somente leitura no banco; isto e uma segunda trava, do lado do codigo.
"""

import pymysql


def conectar(db_cfg):
    return pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **db_cfg)


def _e_somente_leitura(sql):
    inicio = sql.lstrip().lstrip("(").lstrip().upper()
    return inicio.startswith("SELECT") or inicio.startswith("WITH")


def consultar(conn, sql):
    """Roda um SELECT e devolve lista de dicts (uma linha = um dict)."""
    if not _e_somente_leitura(sql):
        raise ValueError("Bloqueado: esta ponte so executa SELECT (usuario viewer).")
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()
