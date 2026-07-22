# -*- coding: utf-8 -*-
"""Ponte ERP -> arquivos dos consumidores (AtacadeRJ).

Extrai (SELECT, usuario viewer) catalogo/vendas/recebimentos/pedidos e escreve,
via camada de projecao, o formato exato de cada consumidor:

  catalogo      -> cotacao/produtos.json  +  detector-estoque/curva_abc.csv  +  detector-salao/curva_abc.csv
  vendas        -> detector-salao/vendas.csv        (sem valor)
                   detector-estoque/vendas.csv       (com valor R$)
  entradas      -> detector-estoque/entradas.csv  +  detector-salao/entradas.csv
  recebimentos  -> detector-salao/recebimentos.csv  +  detector-estoque/recebimentos.csv
  pedidos       -> detector-estoque/pedidos.csv
  pedidos-venda -> cotacao/pedidos_venda_dav.csv    (auditoria de desconto do app)
  vendas-mensal -> dashboard/vendas_mensal.json + .html (dashboard auto-contido:
                   unidades vendidas por item nos meses FECHADOS; abre local)
  catalogo e pedidos-venda tambem escrevem cotacao/catalogo_bridge.json —
  o ARQUIVO UNICO (catalogo mesclado + pedidos de venda) que o robo de upload
  sobe no artifact do claude.ai pelo botao "Catalogo" do app
  historico-cliente -> historico_cliente.csv do app recuperacao-itens
                   (Recuperar+Ampliar; compras por cliente, ~24 meses de DAV)
  exposicao     -> exposicao/vendas_canal.csv + exposicao/catalogo_exposicao.csv
                   (venda por item/dia/canal em unidades + caixa-mae/prateleira;
                    base do calculo de MIN/MAX de exposicao — janela longa,
                    agenda MENSAL propria, como o historico-cliente)
  painel        -> painel/index.html + dados_painel.json (Painel de Compras
                   TV+PC: validade x relampago, ruptura, cobranca, concorrente)
  listagem      -> listagem/catalogo_listagem.csv + vendas_diarias.csv +
                   entradas_fornecedor.csv + negociacao.csv (app
                   listagem-fornecedor; janela PROPRIA de 180d, agenda propria,
                   NAO entra no `all` — mesmo espirito do `exposicao`)

Uso:
  python src/bridge.py --demo                # gera tudo com dados falsos (sem banco)
  python src/bridge.py                       # gera tudo lendo o MySQL (config.local.json)
  python src/bridge.py --only catalogo       # so o catalogo (para o agendamento 3-5x/dia)
  python src/bridge.py --only movimentos     # vendas+recebimentos+pedidos (agendamento diario)
  python src/bridge.py --only exposicao      # base do MIN/MAX de exposicao (mensal)
  python src/bridge.py --only painel         # painel de compras (06:00 + pos-catalogo)
  python src/bridge.py --only listagem       # listagem por fornecedor (manual/agenda propria)
  python src/bridge.py --config caminho.json # usa outro arquivo de config
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta

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


def coletar(cfg, usar_demo, alvo="all"):
    """Devolve as 8 tabelas brutas, do banco ou do demo. Duas sao condicionadas
    ao alvo porque tem janela longa e agenda propria: o historico de cliente
    (~24 meses de DAV) e a exposicao (~400 dias de cupom do DORSAL). Nenhuma
    das duas roda nos agendamentos de catalogo/movimentos — e vice-versa, os
    jobs delas nao pagam as outras queries."""
    janela = cfg.get("janela_dias", 120)
    janela_ent = cfg.get("janela_entradas_dias", 180)
    janela_pv = cfg.get("janela_pedidos_venda_dias", 7)
    meses_vm = cfg.get("vendas_mensal_meses", 6)
    meses_hc = cfg.get("historico_cliente_meses", 24)
    janela_exp = cfg.get("exposicao", {}).get("janela_dias", 400)
    pdvs_atacado = cfg.get("exposicao", {}).get("pdvs_atacado", [11, 12])
    quer_hc = alvo in ("all", "historico-cliente")
    quer_exp = alvo in ("all", "exposicao")
    so_hc = alvo == "historico-cliente"
    so_exp = alvo == "exposicao"
    leve = so_hc or so_exp          # alvos de janela longa: nao pagam o resto

    if usar_demo:
        vc = demo_data.vendas_canal(janela_exp) if quer_exp else []
        if leve:
            hc = demo_data.historico_cliente() if quer_hc else []
            cat = demo_data.catalogo() if quer_exp else []
            return cat, [], [], [], [], [], hc, vc, []
        return (demo_data.catalogo(), demo_data.vendas(janela),
                demo_data.entradas(janela_ent), demo_data.pedidos(), [],
                demo_data.vendas_mensal(),
                demo_data.historico_cliente() if quer_hc else [], vc,
                demo_data.validades() if hasattr(demo_data, "validades") else [])

    import db
    conn = db.conectar(cfg["db"])
    try:
        cat = ven = ent = ped = pv = vm = val = []
        # a exposicao precisa do catalogo (caixa-mae/prateleira), mas nao das
        # queries de movimento
        if so_exp:
            cat = db.consultar(conn, queries.CATALOGO)
        elif not so_hc:
            cat = db.consultar(conn, queries.CATALOGO)
            ven = db.consultar(conn, queries.VENDAS.format(janela=int(janela)))
            ent = db.consultar(conn, queries.ENTRADAS.format(janela_entradas=int(janela_ent)))
            ped = db.consultar(conn, queries.PEDIDOS)
            pv = db.consultar(conn, queries.PEDIDOS_VENDA.format(janela_pedidos_venda=int(janela_pv)))
            vm = db.consultar(conn, queries.VENDAS_MENSAL.format(meses_fechados=int(meses_vm)))
            # VALIDADES e a UNICA query com nome de coluna ainda nao confirmado
            # (dtValidade — ver o comentario em queries.py). Se o ERP usar outro
            # nome, ela falha SOZINHA e o resto da ponte segue normal: o catalogo
            # so sai sem validade, e o app simplesmente nao mostra a linha.
            # NUNCA deixe esta query derrubar a coleta inteira.
            try:
                val = db.consultar(conn, queries.VALIDADES.format(janela_entradas=int(janela_ent)))
            except Exception as e:
                val = []
                print("AVISO: a query VALIDADES falhou — o catalogo sai SEM validade.\n"
                      f"       Motivo: {e}\n"
                      "       Descubra o nome certo da coluna com:\n"
                      "         python src/inspect_schema.py validade vencimento lote\n"
                      "       e corrija `i.dtValidade` em src/queries.py (VALIDADES).")
        hc = (db.consultar(conn, queries.HISTORICO_CLIENTE.format(historico_meses=int(meses_hc)))
              if quer_hc else [])
        vc = (db.consultar(conn, queries.VENDAS_CANAL.format(
                  janela_exposicao=int(janela_exp),
                  pdvs_atacado=", ".join(str(int(p)) for p in pdvs_atacado)))
              if quer_exp else [])
    finally:
        conn.close()
    return cat, ven, ent, ped, pv, vm, hc, vc, val


def escrever(cfg, cat, ven, ent, ped, pv, vm, hc, vc, alvo, val=None):
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
        n = projections.curva_abc_csv(cat, os.path.join(salao, "curva_abc.csv"))
        rel.append(f"detector-salao/curva_abc.csv: {n}")
        n = projections.prateleira_csv(cat, os.path.join(salao, "prateleira.csv"))
        rel.append(f"detector-salao/prateleira.csv: {n}")

    if alvo in ("all", "movimentos", "vendas"):
        n = projections.vendas_csv(ven, os.path.join(salao, "vendas.csv"))
        rel.append(f"detector-salao/vendas.csv: {n}")
        n = projections.vendas_csv(ven, os.path.join(estoque, "vendas.csv"),
                                   incluir_valor=True, incluir_custo=True)
        rel.append(f"detector-estoque/vendas.csv: {n}")

    if alvo in ("all", "movimentos", "entradas", "recebimentos"):
        # entradas.csv (todas as entregas, ~6 meses) -> os dois detectores
        n = projections.entradas_csv(ent, os.path.join(estoque, "entradas.csv"))
        rel.append(f"detector-estoque/entradas.csv: {n}")
        n = projections.entradas_csv(ent, os.path.join(salao, "entradas.csv"))
        rel.append(f"detector-salao/entradas.csv: {n}")
        # recebimentos.csv (ultima entrega por item, derivada) -> os dois detectores
        n = projections.recebimentos_csv(ent, os.path.join(salao, "recebimentos.csv"))
        rel.append(f"detector-salao/recebimentos.csv: {n}")
        n = projections.recebimentos_csv(ent, os.path.join(estoque, "recebimentos.csv"))
        rel.append(f"detector-estoque/recebimentos.csv: {n}")

    if alvo in ("all", "movimentos", "pedidos"):
        n = projections.pedidos_csv(ped, os.path.join(estoque, "pedidos.csv"))
        rel.append(f"detector-estoque/pedidos.csv: {n}")

    if alvo in ("all", "movimentos", "pedidos-venda"):
        caminho = saida.get("cotacao_pedidos_venda_csv") or os.path.join(
            os.path.dirname(saida["cotacao_produtos_json"]), "pedidos_venda_dav.csv")
        n = projections.pedidos_venda_csv(pv, caminho)
        rel.append(f"cotacao/pedidos_venda_dav.csv: {n}")

    if alvo in ("all", "catalogo", "movimentos", "pedidos-venda"):
        caminho = saida.get("catalogo_bridge_json") or os.path.join(
            os.path.dirname(saida["cotacao_produtos_json"]), "catalogo_bridge.json")
        np, nped = projections.catalogo_bridge_json(
            cat, pv, caminho, gerado_em, cfg.get("janela_pedidos_venda_dias", 7),
            validades=val)
        _nvd = len({int(r["codigo"]) for r in (val or []) if r.get("validade")})
        rel.append(f"cotacao/catalogo_bridge.json: {np} produtos + {nped} pedidos de venda"
                   + (f" + validade em {_nvd} produtos" if _nvd else " (sem validade)"))
        # copia para a pasta do upload MANUAL (Area de Trabalho, so este arquivo):
        # o operador acha na hora, e o app confere data + janela de horario
        pasta_manual = saida.get("upload_manual_dir") or os.path.join(
            os.path.expanduser("~"), "Desktop", "AtacadeRJ-Banco")
        try:
            os.makedirs(pasta_manual, exist_ok=True)
            shutil.copyfile(caminho, os.path.join(pasta_manual, "catalogo_bridge.json"))
            rel.append(f"upload manual: {os.path.join(pasta_manual, 'catalogo_bridge.json')}")
        except OSError as e:
            rel.append(f"upload manual: FALHOU a copia ({e})")
        # idem para a AUDITORIA: pasta dedicada com UM arquivo (so os pedidos
        # fechados ONTEM), sobrescrito a cada janela — contingencia da aba 🔍
        try:
            with open(caminho, encoding="utf-8") as f:
                _cb = json.load(f)
            # loja nao abre domingo: na segunda, o "dia anterior" e o SABADO
            _d = datetime.now() - timedelta(days=1)
            if _d.weekday() == 6:  # domingo
                _d -= timedelta(days=1)
            _ontem = _d.strftime("%Y-%m-%d")
            _peds = [p for p in _cb.get("pedidos_venda", {}).get("pedidos", [])
                     if str(p.get("dia"))[:10] == _ontem]
            pasta_aud = saida.get("upload_manual_auditoria_dir") or os.path.join(
                os.path.expanduser("~"), "Desktop", "AtacadeRJ-Auditoria")
            os.makedirs(pasta_aud, exist_ok=True)
            _arq_aud = os.path.join(pasta_aud, "auditoria_bridge.json")
            with open(_arq_aud, "w", encoding="utf-8") as f:
                json.dump({"origem": "erp-bridge-auditoria", "gerado_em": gerado_em,
                           "janela_dias": 1, "pedidos": _peds}, f, ensure_ascii=False)
            rel.append(f"upload manual auditoria: {_arq_aud} ({len(_peds)} pedidos de ontem)")
        except (OSError, ValueError) as e:
            rel.append(f"upload manual auditoria: FALHOU ({e})")

    if alvo in ("all", "historico-cliente"):
        caminho = saida.get("historico_cliente_csv")
        if caminho:
            n = projections.historico_cliente_csv(hc, caminho)
            rel.append(f"recuperacao-itens/historico_cliente.csv: {n}")
        else:
            rel.append("historico_cliente.csv: PULADO (falta saida.historico_cliente_csv no config)")

    if alvo in ("all", "exposicao"):
        exp_dir = saida.get("exposicao_dir") or os.path.join(RAIZ, "saida", "exposicao")
        n = projections.vendas_canal_csv(vc, os.path.join(exp_dir, "vendas_canal.csv"))
        rel.append(f"exposicao/vendas_canal.csv: {n}")
        n = projections.catalogo_exposicao_csv(
            cat, os.path.join(exp_dir, "catalogo_exposicao.csv"))
        rel.append(f"exposicao/catalogo_exposicao.csv: {n}")

    if alvo in ("all", "movimentos", "vendas-mensal"):
        dash_dir = saida.get("dashboard_dir") or os.path.join(RAIZ, "saida", "dashboard")
        ni, nm = projections.vendas_mensal_dashboard(
            vm, os.path.join(dash_dir, "vendas_mensal.json"),
            os.path.join(dash_dir, "vendas_mensal.html"), gerado_em)
        rel.append(f"dashboard/vendas_mensal.html: {ni} itens x {nm} meses fechados")

    return rel


def coletar_listagem(cfg, usar_demo):
    """Alvo `listagem` tem agenda propria (janela 180d) e NAO roda no `all`:
    nao pagar 180d de vendas nos jobs de catalogo/movimentos dos detectores."""
    janela = int(cfg.get("listagem", {}).get("janela_dias", 180))
    if usar_demo:
        return (demo_data.catalogo(), demo_data.vendas(janela),
                demo_data.entradas_fornecedor(janela), demo_data.negociacao())
    import db
    conn = db.conectar(cfg["db"])
    try:
        cat = db.consultar(conn, queries.CATALOGO)
        ven = db.consultar(conn, queries.VENDAS.format(janela=janela))
        entf = db.consultar(conn, queries.ENTRADAS_FORNECEDOR.format(
            janela_listagem=janela))
        neg = db.consultar(conn, queries.NEGOCIACAO_FORNECEDOR)
    finally:
        conn.close()
    return cat, ven, entf, neg


def escrever_listagem(cfg, cat, ven, entf, neg):
    destino = cfg["saida"].get("listagem_dir") or os.path.join(
        RAIZ, "saida", "listagem")
    os.makedirs(destino, exist_ok=True)
    rel = []
    n = projections.catalogo_listagem_csv(cat, os.path.join(destino, "catalogo_listagem.csv"))
    rel.append(f"listagem/catalogo_listagem.csv: {n}")
    n = projections.vendas_csv(ven, os.path.join(destino, "vendas_diarias.csv"))
    rel.append(f"listagem/vendas_diarias.csv: {n}")
    n = projections.entradas_fornecedor_csv(entf, os.path.join(destino, "entradas_fornecedor.csv"))
    rel.append(f"listagem/entradas_fornecedor.csv: {n}")
    n = projections.negociacao_csv(neg, os.path.join(destino, "negociacao.csv"))
    rel.append(f"listagem/negociacao.csv: {n}")
    return rel


def main():
    ap = argparse.ArgumentParser(description="Ponte ERP -> consumidores AtacadeRJ")
    ap.add_argument("--demo", action="store_true", help="usa dados falsos, sem tocar no banco")
    ap.add_argument("--only", default="all",
                    choices=["all", "catalogo", "movimentos", "vendas", "entradas", "recebimentos", "pedidos", "pedidos-venda", "vendas-mensal", "historico-cliente", "exposicao", "painel", "listagem"],
                    help="qual bloco gerar (default: all)")
    ap.add_argument("--config", default=None, help="caminho do config (default: config.local.json)")
    args = ap.parse_args()

    inicio = datetime.now()
    try:
        cfg = (json.load(open(os.path.join(RAIZ, "config.example.json"), encoding="utf-8"))
               if args.demo else carregar_config(args.config))
        relatorio = []
        if args.only == "listagem":
            # agenda propria (janela 180d), NAO entra no `all` — desvio ANTES
            # da coleta padrao (mesmo cfg ja carregado acima, demo ou real)
            cat, ven, entf, neg = coletar_listagem(cfg, args.demo)
            relatorio = escrever_listagem(cfg, cat, ven, entf, neg)
        elif args.only != "painel":
            cat, ven, ent, ped, pv, vm, hc, vc, val = coletar(cfg, args.demo, args.only)
            relatorio = escrever(cfg, cat, ven, ent, ped, pv, vm, hc, vc, args.only, val)
        if args.only in ("all", "painel"):
            import painel_compras
            relatorio += painel_compras.rodar(cfg, usar_demo=args.demo)
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
