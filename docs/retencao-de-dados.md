# Matriz de retenção de dados

> Fonte para a política de privacidade (CARD-052). Cada linha cita a regra
> **executável** que a cumpre — se a linha não tem mecanismo, ela é promessa,
> não política. Escrita no CARD-017 (2026-10-01).

| Dado | Onde | Quanto tempo | Quem cumpre | Origem |
|---|---|---|---|---|
| Fala do aluno (áudio enviado) | bucket, tag `retention=input` | **7 dias** | lifecycle do bucket | ADR-0024, `RETENTION_INPUT` |
| Trechos da resposta (áudio por frase) | bucket, tag `retention=reply-chunk` | **1 dia** | lifecycle do bucket | ADR-0024, `RETENTION_REPLY_CHUNK` |
| Resposta inteira (áudio concatenado) | bucket, tag `retention=reply-full` | **90 dias** | lifecycle do bucket | ADR-0024, `RETENTION_REPLY_FULL` |
| Transcrição, resposta em texto, correções, traduções | Postgres | até o aluno excluir a conta | delete de conta | ADR-0069 |
| E-mail, hash de senha, tokens de sessão, vínculo social | Postgres | até o aluno excluir a conta | `ON DELETE CASCADE` de `students` | ADR-0069, ADR-0070 |
| Linha de custo (`usage_events`: tokens, duração, modelo) | Postgres | indefinido, **anonimizada** na exclusão (`student_id → NULL`) | `ON DELETE SET NULL` | ADR-0051, ADR-0069 |

## Garantias e ressalvas

- **As regras do bucket são verificadas no boot do worker**: sem elas, ou com
  TTLs diferentes da configuração, o worker não sobe (ADR-0075). Aplicar:
  `uv run voicecoach-storage-setup`.
- **"Até N dias" e não "exatamente N dias":** o lifecycle do S3/MinIO apaga
  em até 24–48 h depois do prazo. A API trata o áudio como indisponível a
  partir do prazo (previsão conservadora), não quando o objeto some.
- **Exclusão de conta** apaga o áudio na hora (`delete_prefix`), sem esperar o
  lifecycle (ADR-0069).
- **Lacuna conhecida:** a regra vale para o storage verificado (MinIO). Num
  provedor S3 real ela precisa ser reconferida no deploy (CARD-055).
