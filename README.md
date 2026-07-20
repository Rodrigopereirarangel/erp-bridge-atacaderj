# erp-bridge-atacaderj

Ponte **única** que extrai do ERP (**Solidcon / SQL Server 2014**, login
**somente-leitura**) e alimenta, sozinha e agendada, todos os sistemas do
AtacadeRJ — **acabando com a exportação manual de relatórios**. Custo
recorrente **R$ 0**; roda local no PC da rede. **Status: em produção no
PC-ponte desde 2026-07-07** (queries validadas ao centavo contra o
consolidado oficial do PDV).

```
                                     ┌─ catalogo   (3-5x/dia) ─┐
ERP SQL Server ──(SELECT apenas)──►  │  vendas       (diário)  │──► arquivos ──► cotação / detectores / pricing
  (Solidcon)      src/bridge.py      │  entradas     (diário)  │
   agendado ↑                        └─ pedidos      (diário) ──┘
```

## O que ele gera (contrato completo em [`docs/CONTRATO-DE-DADOS.md`](docs/CONTRATO-DE-DADOS.md))

| Bloco | Vira | Para quem |
|---|---|---|
| **catalogo** | `produtos.json` (chaves `c,p,q,v,vu,vp,custo,cv`) + `curva_abc.csv` | Cotação HTML; detectores |
| **vendas** | `vendas.csv` (salão) + `vendas.csv` (estoque, com R$ e `custo_venda`) | os 2 detectores; pricing (giro deriva daqui) |
| **entradas** | `entradas.csv` (todas as entregas ~6 meses) + `recebimentos.csv` (última, derivada) | detector de estoque (proxy de estoque); detector de salão |
| **pedidos** | `pedidos.csv` (pedidos de compra abertos) | detector de estoque (cruzamento "já comprei?") |
| **painel** | `painel/index.html` (Painel de Compras TV+PC: validade×relâmpago, ruptura, cobrança, concorrente) | setor de compras (TV da sala + PCs) |

## Começar (2 minutos, sem banco)

```bash
pip install -r requirements.txt
python src/bridge.py --demo
```
Isso gera os arquivos com **dados falsos** para você conferir o **formato** — sem
tocar no ERP. Os arquivos vão para os caminhos de `config.example.json > saida`.

## Ligar no banco de verdade

1. `copy config.example.json config.local.json` e preencha `db` (tipo
   `sqlserver`, host, login somente-leitura, senha, database `Solidcon`) e os
   caminhos de `saida`. **`config.local.json` não é versionado** (tem a senha).
2. As queries **já estão preenchidas** com o schema real do Solidcon
   (`src/queries.py`, T-SQL — o cabeçalho documenta os fatos do schema).
   Se algo mudar no ERP: `python src/inspect_schema.py <termos>` para explorar.
3. Teste: `python src/bridge.py --only catalogo`
4. Agende: em PowerShell (Admin), `./scripts/register-tasks.ps1`
   (catálogo 08/12/15/18h; movimentos 05:00, antes do detector das 05:30).

## Painel de Compras (TV + PC)

Gerado por `python src/bridge.py --only painel` (agendado 06:00 + pós-catálogo;
`./scripts/register-painel-tasks.ps1` registra geração + servidor HTTP).
Acesso: `http://<ip-do-ponte>:8477/` — nos PCs é interativo (clique abre o
detalhe com filtro); na TV use `http://<ip-do-ponte>:8477/#tv` em tela cheia
(rodízio automático, recarrega sozinho). Fontes e regras: spec
`docs/superpowers/specs/2026-07-20-painel-compras-design.md`.

## Onde roda (topologia segura)

- **Servidor SQL Server + apps do ERP** → **NÃO recebe nada. Intocado.** Nenhuma
  instalação, nenhum processo, nenhum arquivo mexido.
- **PC-ponte** (outra máquina, na mesma rede do servidor) → roda **este** script.
  Conecta no SQL Server **por TCP** com login somente-leitura (só `SELECT`) e
  grava os arquivos **localmente**, na pasta que os consumidores (cotação/detectores) leem.
- **A IA nunca roda no servidor.** Ela só ajuda a escrever os `SELECT`s; o que roda
  no PC-ponte é este script fixo, read-only.

Boa prática no PC-ponte: rodar a Tarefa Agendada sob um **usuário Windows dedicado,
sem admin**, com permissão de escrita **só na pasta de saída**.

## Segurança

- O login do banco só faz `SELECT`. O código tem uma **segunda trava**
  (`src/db.py` recusa qualquer coisa que não seja `SELECT`/`WITH`).
- Preço/custo **não saem da rede local**. A senha fica só em `config.local.json`.

## Estado

**Funcionando em produção** (2026-07-07): os 4 `SELECT`s estão preenchidos com o
schema real do Solidcon e validados — vendas batem ao centavo com o consolidado
oficial do PDV. Origem de cada dado: `docs/CONTRATO-DE-DADOS.md`. Pendências no
`STATUS.md` (agendar tarefas + ligar o HTML da cotação).
