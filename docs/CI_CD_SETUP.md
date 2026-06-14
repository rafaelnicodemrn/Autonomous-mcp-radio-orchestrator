# Setup de CI/CD — RadioIA

Checklist de configuração única para habilitar o pipeline
`push → CI → merge main → CD`. A maior parte exige acesso ao servidor de
produção (SSH) e às configurações do repositório no GitHub — passos manuais,
não automatizáveis.

## 0. Acesso ao repositório (resolvido)

O projeto está hospedado em
`https://github.com/rafaelnicodemrn/Autonomous-mcp-radio-orchestrator`
(`origin`), com `rafaelnicodemrn` como **Admin**. `main` e `develop` foram
enviados, o ambiente `production` foi criado e a branch protection de `main`
já está configurada via `gh api` (seções 3 e 4). Falta apenas configurar os
Secrets (seção 2) com valores reais.

## 1. Servidor de produção (GCP VM, via Cloud Console SSH)

Gerar uma chave SSH dedicada para o GitHub Actions e restringir o `sudo` ao
mínimo necessário:

```bash
# 1. Gerar par de chaves SSH dedicado para GitHub Actions
ssh-keygen -t ed25519 -C "github-actions-radioia" -f ~/.ssh/github_actions_key -N ""

# 2. Adicionar chave publica ao authorized_keys
cat ~/.ssh/github_actions_key.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# 3. Exibir chave PRIVADA (copiar para GitHub Secrets)
cat ~/.ssh/github_actions_key
# Copiar TODO o conteudo, incluindo as linhas BEGIN/END, para:
# GitHub -> Settings -> Secrets and variables -> Actions -> GCLOUD_SSH_PRIVATE_KEY

# 4. Configurar sudo sem senha APENAS para os comandos do radioia-bot
echo "rafaelnicodemrn ALL=(ALL) NOPASSWD: /bin/systemctl restart radioia-bot, /bin/systemctl is-active radioia-bot, /bin/journalctl -u radioia-bot*" | sudo tee /etc/sudoers.d/github-actions-radioia

# 5. Verificar que o projeto tem git configurado (necessario para rollback)
cd ~/radioIA && git log --oneline -3
```

> Depois de gerar a chave privada, apague-a do histórico do shell
> (`history -d <linha>` ou feche a sessão) — ela só deve existir no GitHub
> Secret e em `~/.ssh/` na VM.

## 2. GitHub Secrets (pendente — valores reais)

**Settings → Secrets and variables → Actions → New repository secret**
(ou `gh secret set <NOME> --env production --body "<valor>"`)

| Secret                  | Valor                                              |
|-------------------------|----------------------------------------------------|
| `GCLOUD_SSH_PRIVATE_KEY` | Conteúdo completo de `~/.ssh/github_actions_key` na VM |
| `TELEGRAM_BOT_TOKEN`     | Token real do bot (para testes de integração futuros) |

> Sem `GCLOUD_SSH_PRIVATE_KEY`, o job `deploy` do `cd.yml` falha na etapa de
> SSH — é o comportamento esperado até este secret ser configurado.

## 3. GitHub Environment `production` (concluído)

Ambiente `production` criado via `gh api`, com
`deployment_branch_policy.protected_branches = true` (restringe deploys a
branches protegidas, ou seja, `main`). Adicionar os secrets da seção 2 ao
ambiente quando disponíveis.

## 4. Branch protection em `main` (concluído)

Configurado via `gh api repos/.../branches/main/protection`:

- Required status checks (strict — branch precisa estar atualizada):
  `Lint (flake8 + black + isort)`, `Testes Automatizados`,
  `Segurança (bandit + pip-audit)`
- `enforce_admins: false` (dono do repo pode mergear mesmo se um check
  falhar, útil para repo pessoal — endurecer depois se desejado)
- Sem exigência de PR review (repo de um único mantenedor)
- Force push e deleção de `main` bloqueados

## 5. Validação pós-setup

1. Abrir um PR de `feature/*` para `develop` (ou `main`) e confirmar que o
   workflow `ci.yml` roda e os checks aparecem no PR.
2. Fazer merge em `main` e acompanhar `cd.yml`:
   - `ci-check` deve reusar o `ci.yml`
   - `deploy` deve sincronizar arquivos, instalar dependências e reiniciar
     `radioia-bot`
   - Em caso de falha, `rollback` deve voltar para o commit anterior
3. Confirmar no servidor:
   ```bash
   sudo systemctl status radioia-bot
   sudo journalctl -u radioia-bot -n 20 --no-pager
   ```
