# Como implementar no PC-ponte — roteiro copiar-e-colar

> Para o **humano** no PC-ponte (`DESKTOP-3BLTBIV`). Este PC não tem acesso à sessão
> onde o design nasceu — **não precisa**: os repositórios carregam tudo (specs, planos
> e este roteiro). O Claude Code daqui executa os planos sozinho.

## 0. Pré-requisitos (uma vez)

Em PowerShell:

```powershell
winget install -e --id Git.Git
winget install -e --id Python.Python.3.12
winget install -e --id OpenJS.NodeJS.LTS   # o repo da cotacao usa scripts node (selar)
irm https://claude.ai/install.ps1 | iex     # Claude Code
```

Feche e reabra o PowerShell. Rode `claude` uma vez para logar na conta Claude.

## 1. Clonar os dois repositórios (privados — o Git abre o navegador para autenticar)

```powershell
cd $HOME
git clone https://github.com/Rodrigopereirarangel/cotacao-auditoria-atacaderj.git
git clone https://github.com/Rodrigopereirarangel/erp-bridge-atacaderj.git
```

(Se já existem: `git pull` em cada um.)

## 2. Sessão 1 — app da cotação (PRIMEIRO: o robô depende dos IDs criados aqui)

```powershell
cd $HOME\cotacao-auditoria-atacaderj
claude
```

Colar este prompt:

> Execute o plano `docs/superpowers/plans/2026-07-07-aceitar-catalogo-bridge.md`
> usando a skill superpowers:executing-plans. Siga as tasks na ordem, respeite as
> Global Constraints (principalmente rodar `npm run selar` após mexer no app),
> pare nos checkpoints para eu revisar, e ao final faça commit e push.

## 3. Sessão 2 — bridge (projeção + robô + tarefas)

```powershell
cd $HOME\erp-bridge-atacaderj
claude
```

Colar este prompt:

> Execute o plano `docs/superpowers/plans/2026-07-07-catalogo-bridge-e-robo.md`
> usando a skill superpowers:executing-plans. Siga as tasks na ordem com TDD,
> pare nos checkpoints, e ao final faça commit e push. A seção "Implantação" do
> plano é manual — NÃO execute; ao terminar, me guie por ela passo a passo,
> executando por comando o que der e me pedindo só o que for manual
> (publicar o artifact, colar o link, logar no navegador do robô).

## 4. O que sobra para o humano (o Claude da Sessão 2 vai te guiar)

1. **Publicar o app como artifact** na conta Claude (com as mudanças da Sessão 1)
   e copiar o link fixo — ele vai no `robo/config_robo.json`.
2. **Logar o navegador do robô**: `python robo/upload_catalogo.py --setup`
   → entrar na conta Claude → fechar o navegador.
3. **Rodada assistida** (olhando a tela): `python src/bridge.py --only catalogo`
   e depois `python robo/upload_catalogo.py`.
4. **Agendar**: `./scripts/register-tasks.ps1` em PowerShell **Admin**.

## 5. Não esquecer — o bridge ainda precisa do schema real do MySQL

Os planos acima deixam a esteira pronta, mas o bridge só gera dados REAIS depois
do passo que já estava pendente no `STATUS.md`: testar o login do `viewer`, rodar
`python src/inspect_schema.py produto preco custo curva venda entrada pedido` e
preencher os 4 `SELECT`s de `src/queries.py`. O `CLAUDE.md` guia isso — basta
dizer ao Claude Code: **"continue pelo STATUS.md"**. Até lá, valide tudo com
`python src/bridge.py --demo`.

## Regra de ouro (vale para as duas sessões)

Sempre que avançar: atualizar o `STATUS.md` (checklist + log) e `git add -A &&
git commit && git push`. **O repositório é a memória do projeto** — é assim que a
próxima sessão (em qualquer PC) retoma sem perder nada.
