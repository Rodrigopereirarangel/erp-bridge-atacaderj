# -*- coding: utf-8 -*-
"""Regra 1 do spec (docs/superpowers/specs/2026-07-22-...-design.md):
1) negociacao com "COTACAO" -> COTACAO, exclusivo (decisao do dono 22/07);
2) senao, fornecedor com MAIOR soma de unidades entregues na janela do CSV
   (6 meses, ja recortada pelo bridge); empate -> entrega mais recente;
   empate de novo -> alfabetico (determinismo);
3) senao, negociacao alterada por ultimo (dt vazia = mais antiga;
   todas vazias -> alfabetico);
4) senao, o consumidor usa SEM_FORNECEDOR."""

SEM_FORNECEDOR = "SEM FORNECEDOR"
COTACAO = "COTACAO"


def _norm(nome):
    return (nome or "").strip().upper()


def atribuir(negociacoes, entradas):
    """-> {codigo: nome do fornecedor} (so codigos presentes nos insumos)."""
    resultado = {}

    neg_por_cod = {}
    for n in negociacoes:
        neg_por_cod.setdefault(n["codigo"], []).append(n)

    ent_por_cod = {}
    for e in entradas:
        if _norm(e["fornecedor"]):
            ent_por_cod.setdefault(e["codigo"], []).append(e)

    for codigo in set(neg_por_cod) | set(ent_por_cod):
        negs = neg_por_cod.get(codigo, [])
        if any(_norm(n["fornecedor"]) == COTACAO for n in negs):
            resultado[codigo] = COTACAO
            continue
        ents = ent_por_cod.get(codigo, [])
        if ents:
            por_forn = {}
            for e in ents:
                nome = e["fornecedor"].strip()
                total, recente = por_forn.get(nome, (0.0, ""))
                por_forn[nome] = (total + float(e["qtd"]),
                                  max(recente, str(e["data"])))
            # maior soma primeiro; empate -> entrega mais recente; e o nome
            # alfabetico como ultimo desempate (determinismo)
            melhor = sorted(por_forn.items(),
                            key=lambda kv: (-kv[1][0],
                                            _data_desc(kv[1][1]), kv[0]))[0]
            resultado[codigo] = melhor[0]
            continue
        if negs:
            escolhido = sorted(
                negs, key=lambda n: (_data_desc(str(n.get("dt_alteracao") or "")),
                                     n["fornecedor"].strip()))[0]
            resultado[codigo] = escolhido["fornecedor"].strip()
    return resultado


def _data_desc(data_iso):
    """Chave de ordenacao: data ISO mais RECENTE primeiro; vazia por ultimo.
    Truque sem datetime: nega cada caractere pelo complemento de ord()."""
    if not data_iso:
        return chr(255)                 # depois de qualquer data invertida
    return "".join(chr(255 - ord(c)) for c in data_iso)
