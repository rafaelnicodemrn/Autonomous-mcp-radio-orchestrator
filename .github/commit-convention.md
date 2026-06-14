# Convenção de commits — RadioIA

Este projeto usa [Conventional Commits](https://www.conventionalcommits.org/).

## Formato

```
<tipo>(<escopo opcional>): <descrição curta no imperativo>
```

## Tipos

| Tipo       | Quando usar                                              |
|------------|-----------------------------------------------------------|
| `feat`     | Nova funcionalidade                                        |
| `fix`      | Correção de bug                                            |
| `refactor` | Mudança de código sem alterar comportamento                |
| `test`     | Adição/ajuste de testes                                    |
| `ci`       | Mudanças em workflows, pipelines, automação                |
| `docs`     | Documentação                                               |
| `chore`    | Manutenção (deps, configs, arquivos de apoio)              |
| `perf`     | Melhoria de performance                                    |

## Escopos comuns

`adaptive`, `telegram`, `profile`, `youtube`, `tts`, `scheduler`, `config`,
`docs`

## Exemplos

```
feat(adaptive): adiciona decay temporal nos pesos
fix(telegram): corrige callback_data acima de 64 bytes
refactor(profile): extrai _calc_recency para função pura
test(adaptive): adiciona testes para calculate_dynamic_weights
ci: adiciona job de lint no GitHub Actions
docs: atualiza DEPLOYMENT.md com novo fluxo CI/CD
chore: atualiza requirements.txt com tenacity 9.x
```
