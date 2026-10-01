/**
 * A configuração da web, lida UMA vez no import — o equivalente do
 * `src/config.ts` do mobile (ADR-0044 §4), sobre `import.meta.env` do Vite.
 *
 * Só variáveis com prefixo `VITE_` chegam ao navegador, e tudo que chega é
 * público: nenhum segredo mora aqui. O client ID Web do Google não é segredo
 * (ADR-0070) — é o mesmo valor que o backend confere como audiência.
 */

export type ConfigDaWeb = {
  /**
   * Vazio = mesma origem (o proxy do Vite em dev, o reverse proxy em
   * produção — ADR-0077). Só muda para apontar a web para outro backend
   * atrás do mesmo domínio.
   */
  apiBaseUrl: string;
  /** `null` = botão do Google escondido; e-mail+senha funciona sem ele. */
  googleClientId: string | null;
  /** Mesmo valor do `app.json > extra` do mobile: regra de produto. */
  limiteGravacaoSegundos: number;
  versao: string;
};

function lerConfig(): ConfigDaWeb {
  const googleClientId = import.meta.env.VITE_GOOGLE_WEB_CLIENT_ID;
  return {
    apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? '',
    googleClientId:
      typeof googleClientId === 'string' && googleClientId.length > 0
        ? googleClientId
        : null,
    limiteGravacaoSegundos: 90,
    versao: __VERSAO_DA_WEB__,
  };
}

export const config = lerConfig();
