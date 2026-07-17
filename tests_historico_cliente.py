# -*- coding: utf-8 -*-
"""Testes da extracao HISTORICO_CLIENTE (sem banco): projecao do CSV, dados
demo e contrato da query. Rodavel direto: `python tests_historico_cliente.py`
— asserts diretos, sem pytest; OK/FALHOU por teste e exit 1 se algo falhar.

Contrato do consumidor (recuperacao-itens-atacaderj/src/motor.py):
cliente;codigo;produto;data;emb;unidades_por_emb;qtde_emb;unidades;valor;custo;grupo
"""
import csv
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import demo_data    # noqa: E402
import projections  # noqa: E402
import queries      # noqa: E402

CAB = ["cliente", "codigo", "produto", "data", "emb", "unidades_por_emb",
       "qtde_emb", "unidades", "valor", "custo", "grupo"]


def _linha(**kw):
    base = {"cliente": "CLIENTE X", "codigo": 2411, "produto": "SUCRILHOS",
            "data": "2026-06-01", "emb": "CX-12", "unidades_por_emb": 12,
            "qtde_emb": 2, "unidades": 24, "valor": 453.6, "custo": 340.8,
            "grupo": "MATINAIS"}
    base.update(kw)
    return base


def _escrever_e_ler(itens):
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "historico_cliente.csv")
        n = projections.historico_cliente_csv(itens, caminho)
        with open(caminho, encoding="utf-8", newline="") as f:
            linhas = list(csv.reader(f, delimiter=";"))
    return n, linhas


def test_cabecalho_11_colunas_terminando_em_grupo():
    n, linhas = _escrever_e_ler([_linha()])
    assert linhas[0] == CAB, f"cabecalho errado: {linhas[0]}"
    assert linhas[0][-1] == "grupo"
    assert n == 1 and len(linhas) == 2


def test_valores_na_ordem_do_contrato():
    _, linhas = _escrever_e_ler([_linha()])
    assert linhas[1] == ["CLIENTE X", "2411", "SUCRILHOS", "2026-06-01", "CX-12",
                         "12", "2", "24", "453.6", "340.8", "MATINAIS"], linhas[1]


def test_grupo_fora_do_mix_vira_vazio():
    # "INATIVOS OU FORA DO MIX" e status de mix, nao familia -> SEM GRUPO
    _, linhas = _escrever_e_ler([
        _linha(grupo="INATIVOS OU FORA DO MIX"),
        _linha(grupo="inativos ou fora do mix "),  # caixa/espaco nao importam
        _linha(grupo=None),
        _linha(grupo="  BEBIDAS  "),               # RTRIM/strip da familia real
    ])
    grupos = [ln[-1] for ln in linhas[1:]]
    assert grupos == ["", "", "", "BEBIDAS"], grupos


def test_grupo_normalizado_conservas_2():
    # "CONSERVAS 2" e a MESMA familia de "CONSERVAS" (grafia da arvore do ERP);
    # sem normalizar, o lookalike do app ve duas familias diferentes
    _, linhas = _escrever_e_ler([_linha(grupo="CONSERVAS 2"),
                                 _linha(grupo="CONSERVAS")])
    grupos = [ln[-1] for ln in linhas[1:]]
    assert grupos == ["CONSERVAS", "CONSERVAS"], grupos


def test_demo_tem_forma_e_contas_consistentes():
    itens = demo_data.historico_cliente()
    assert len(itens) >= 8, "demo minguado"
    for r in itens:
        assert sorted(r.keys()) == sorted(CAB), f"chaves erradas: {sorted(r.keys())}"
        assert r["unidades"] == r["qtde_emb"] * r["unidades_por_emb"], r
        assert r["valor"] > r["custo"] > 0, r          # totais da linha, venda > custo
        assert len(str(r["data"])) == 10, r["data"]     # ISO yyyy-mm-dd
    # cobre os dois casos de grupo que a projecao precisa tratar
    grupos = {r["grupo"] for r in itens}
    assert "INATIVOS OU FORA DO MIX" in grupos and "" in grupos, grupos


def test_demo_passa_pela_projecao():
    itens = demo_data.historico_cliente()
    n, linhas = _escrever_e_ler(itens)
    assert n == len(itens)
    assert all(ln[-1] != "INATIVOS OU FORA DO MIX" for ln in linhas[1:])


def test_query_respeita_os_fatos_do_schema():
    q = queries.HISTORICO_CLIENTE
    assert "{historico_meses}" in q                      # janela vem do config
    assert "COALESCE(ps.inMorto, 0) = 0" in q            # cliente ativo (NULL = vivo)
    assert "VW_MGN_PRODUTO" in q and "Departamento" in q  # familia = raiz da arvore
    assert "inEntrada = 0" in q                          # pedido de VENDA (DAV)
    assert "dtAtendido" in q                             # emissao, nao dtPedido
    assert "LEFT JOIN dbo.VW_MGN_PRODUTO" in q           # item sem familia nao some
    assert "i.qtPedidoItem > 0" in q                     # item zerado nao e compra
    assert "LTRIM(RTRIM(ps.nmPessoa))" in q              # nome sem espaco na borda
    for alias in CAB:
        assert f"AS {alias}" in q, f"query nao expoe a coluna {alias}"


TESTES = [
    test_cabecalho_11_colunas_terminando_em_grupo,
    test_valores_na_ordem_do_contrato,
    test_grupo_fora_do_mix_vira_vazio,
    test_grupo_normalizado_conservas_2,
    test_demo_tem_forma_e_contas_consistentes,
    test_demo_passa_pela_projecao,
    test_query_respeita_os_fatos_do_schema,
]


def main():
    falhas = 0
    for teste in TESTES:
        nome = teste.__name__
        try:
            teste()
            print(f"OK    {nome}")
        except AssertionError as e:
            falhas += 1
            print(f"FALHOU {nome}: {e}")
        except Exception as e:  # erro inesperado tambem conta como falha
            falhas += 1
            print(f"ERRO   {nome}: {type(e).__name__}: {e}")

    total = len(TESTES)
    print(f"\n{total - falhas}/{total} passaram")
    if falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()
