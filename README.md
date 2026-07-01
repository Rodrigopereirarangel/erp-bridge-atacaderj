# erp-bridge-atacaderj

Ponte **única** que extrai do ERP (MySQL, usuário **`viewer` somente-leitura**) e
alimenta, sozinha e agendada, todos os sistemas do AtacadeRJ — **acabando com a
exportação manual de relatórios**. Custo recorrente **R$ 0**; roda local no PC da rede.

```
                                 ┌─ catalogo   (3-5x/dia) ─┐
ERP MySQL ──(viewer, SELECT)──►  │  vendas       (diário)  │──► arquivos ──► cotação / detectores / pricing
 (só leitura)   src/bridge.py    │  recebimentos (diário)  │
   agendado ↑                    └─ pedidos      (diário) ──┘
```

## O que ele gera (contrato completo em [`docs/CONTRATO-DE-DADOS.md`](docs/CONTRATO-DE-DADOS.md))

| Bloco | Vira | Para quem |
|---|---|---|
| **catalogo** | `produtos.json` (chaves `c,p,q,v,vu,vp,custo,cv`) + `curva_abc.csv` | Cotação HTML; detectores |
| **vendas** | `vendas.csv` (salão, sem valor) + `vendas.csv` (estoque, com R$) | os 2 detectores; pricing (giro deriva daqui) |
| **recebimentos** | `recebimentos.csv` (última entrega) | os 2 detectores |
| **pedidos** | `pedidos.csv` (pedidos de compra abertos) | detector de estoque (cruzamento "já comprei?") |

## Começar (2 minutos, sem banco)

```bash
pip install -r requirements.txt
python src/bridge.py --demo
```
Isso gera os arquivos com **dados falsos** para você conferir o **formato** — sem
tocar no ERP. Os arquivos vão para os caminhos de `config.example.json > saida`.

## Ligar no banco de verdade

1. `copy config.example.json config.local.json` e preencha `db` (host, `viewer`, senha, database)
   e os caminhos de `saida`. **`config.local.json` não é versionado** (tem a senha).
2. Abra `src/queries.py` e troque os **`--TODO`** (nomes reais de tabela/coluna). É o
   único lugar amarrado ao ERP.
3. Teste: `python src/bridge.py --only catalogo`
4. Agende: em PowerShell (Admin), `./scripts/register-tasks.ps1`
   (catálogo 08/12/15/18h; movimentos 05:00, antes do detector das 05:30).

## Segurança

- Usuário **`viewer`** só faz `SELECT`. O código tem uma **segunda trava**
  (`src/db.py` recusa qualquer coisa que não seja `SELECT`/`WITH`).
- Preço/custo **não saem da rede local**. A senha fica só em `config.local.json`.

## Estado

Design/scaffold pronto e validável por `--demo`. **Falta preencher os `SELECT`s**
com o schema real — ver a tabela "origem no ERP" em `docs/CONTRATO-DE-DADOS.md`.
