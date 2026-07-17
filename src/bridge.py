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
    """Devolve as 7 tabelas brutas, do banco ou do demo. So o historico de
    cliente e condicionado ao alvo: a janela e longa (~24 meses de DAV), entao
    ele nao roda nos agendamentos de catalogo/movimentos — e vice-versa, o job
    das 01:00 (--only historico-cliente) nao paga as outras 6 queries."""
    janela = cfg.get("janela_dias", 120)
    janela_ent = cfg.get("janela_entradas_dias", 180)
    janela_pv = cfg.get("janela_pedidos_venda_dias", 7)
    meses_vm = cfg.get("vendas_mensal_meses", 6)
    meses_hc = cfg.get("historico_cliente_meses", 24)
    quer_hc = alvo in ("all", "historico-cliente")
    so_hc = alvo == "historico-cliente"
    if usar_demo:
        if so_hc:
            return [], [], [], [], [], [], demo_data.historico_cliente()
        return (demo_data.catalogo(), demo_data.vendas(janela),
                demo_data.entradas(janela_ent), demo_data.pedidos(), [],
                demo_data.vendas_mensal(),
                demo_data.historico_cliente() if quer_hc else [])

    import db
    conn = db.conectar(cfg["db"])
    try:
        cat = ven = ent = ped = pv = vm = []
        if not so_hc:
            cat = db.consultar(conn, queries.CATALOGO)
            ven = db.consultar(conn, queries.VENDAS.format(janela=int(janela)))
            ent = db.consultar(conn, queries.ENTRADAS.format(janela_entradas=int(janela_ent)))
            ped = db.consultar(conn, queries.PEDIDOS)
            pv = db.consultar(conn, queries.PEDIDOS_VENDA.format(janela_pedidos_venda=int(janela_pv)))
            vm = db.consultar(conn, queries.VENDAS_MENSAL.format(meses_fechados=int(meses_vm)))
        hc = (db.consultar(conn, queries.HISTORICO_CLIENTE.format(historico_meses=int(meses_hc)))
              if quer_hc else [])
    finally:
        conn.close()
    return cat, ven, ent, ped, pv, vm, hc


def escrever(cfg, cat, ven, ent, ped, pv, vm, hc, alvo):
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
            cat, pv, caminho, gerado_em, cfg.get("janela_pedidos_venda_dias", 7))
        rel.append(f"cotacao/catalogo_bridge.json: {np} produtos + {nped} pedidos de venda")
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

    if alvo in ("all", "movimentos", "vendas-mensal"):
        dash_dir = saida.get("dashboard_dir") or os.path.join(RAIZ, "saida", "dashboard")
        ni, nm = projections.vendas_mensal_dashboard(
            vm, os.path.join(dash_dir, "vendas_mensal.json"),
            os.path.join(dash_dir, "vendas_mensal.html"), gerado_em)
        rel.append(f"dashboard/vendas_mensal.html: {ni} itens x {nm} meses fechados")

    return rel


def main():
    ap = argparse.ArgumentParser(description="Ponte ERP -> consumidores AtacadeRJ")
    ap.add_argument("--demo", action="store_true", help="usa dados falsos, sem tocar no banco")
    ap.add_argument("--only", default="all",
                    choices=["all", "catalogo", "movimentos", "vendas", "entradas", "recebimentos", "pedidos", "pedidos-venda", "vendas-mensal", "historico-cliente"],
                    help="qual bloco gerar (default: all)")
    ap.add_argument("--config", default=None, help="caminho do config (default: config.local.json)")
    args = ap.parse_args()

    inicio = datetime.now()
    try:
        cfg = (json.load(open(os.path.join(RAIZ, "config.example.json"), encoding="utf-8"))
               if args.demo else carregar_config(args.config))
        cat, ven, ent, ped, pv, vm, hc = coletar(cfg, args.demo, args.only)
        relatorio = escrever(cfg, cat, ven, ent, ped, pv, vm, hc, args.only)
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
