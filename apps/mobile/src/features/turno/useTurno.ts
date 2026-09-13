/**
 * A máquina de estados de um turn, do upload ao último trecho tocado.
 *
 * É o objetivo de aprendizado do CARD-012: async na UI de React Native com
 * `AbortController`, backoff, e o **caminho triste como cidadão de primeira
 * classe**. Três coisas aqui não têm paralelo no React web:
 *
 * 1. **O `AbortController` sobrevive à troca de tela.** Ele não é estado do
 *    componente: é o que cancela uma conexão HTTP viva. Por isso mora num
 *    `useRef` e é abortado em transições de máquina, não em `useEffect` de
 *    render.
 * 2. **`AppState` é um evento real.** Ir para background não é uma ficção de
 *    visibilidade como na web: o sistema pode congelar o JavaScript e derrubar a
 *    conexão. Voltar exige **reconectar com `Last-Event-ID`** (ADR-0041), e não
 *    "continuar de onde parou", que não existe.
 * 3. **A `Idempotency-Key` nasce ao PARAR DE GRAVAR**, não dentro do envio.
 *    Chave gerada por tentativa = turn duplicado por retry, que é exatamente o
 *    que o ADR-0042 existe para impedir.
 *
 * **Os dois caminhos de entrega são exercitados** (ADR-0026 item 4): SSE quando
 * `config.sseHabilitado`, `GET /v1/turns/{id}` com backoff quando não — ou
 * quando o stream falha. O recuo que ninguém testa apodrece.
 */

import {
  type Cliente,
  type components,
  criarCliente,
  type EventoDoTurn,
  type Trecho,
  type Turn,
} from '@voicecoach/api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AppState, type AppStateStatus } from 'react-native';

import { config } from '@/config';
import { useSessao } from '@/features/auth/useSessao';
import {
  type ConteudoDeExcecao,
  conteudoDoErro,
  conteudoDoTravamento,
} from '@/features/excecoes/conteudoDaExcecao';
import { lerComoBlob } from '@/features/turno/arquivoLocal';
import { intervalos, MARCOS_VAZIOS, type Marcos } from '@/features/turno/marcos';
import {
  RESUMO_VAZIO,
  type ResumoDaSessao,
  type Severidade,
  type TipoDeCorrecao,
} from '@/features/turno/rotulosDeCorrecao';
import {
  prepararParaTocar,
  useFilaDePlayback,
} from '@/features/turno/useFilaDePlayback';

export type EstadoDoTurn =
  | 'ocioso'
  | 'enviando'
  | 'transcrevendo'
  | 'ouvindo'
  | 'concluido'
  | 'falhou';

/**
 * O botão `traduzir` (CARD-058). `ocioso` cobre "ainda não pedi" — não há
 * distinção entre "não tem" e "não sei ainda", igual à convenção de
 * `correcoes`.
 */
export type FaseDaTraducao = 'ocioso' | 'traduzindo' | 'traduzido' | 'falhou';

export type EstadoDeTraducao = {
  fase: FaseDaTraducao;
  texto: string | null;
};

const TRADUCAO_OCIOSA: EstadoDeTraducao = { fase: 'ocioso', texto: null };

/**
 * Uma correção tipada (CARD-016/CARD-013) — não mais os quatro campos
 * legados. Os nomes em pt-BR espelham `CorrectionPayload`, campo a campo:
 * `tipo`←`type`, `corrigido`←`corrected_form`, `explicacao`←`explanation`,
 * `severidade`←`severity`. `original`/`index` já eram pt-BR-compatíveis.
 */
export type Correcao = {
  index: number;
  tipo: TipoDeCorrecao;
  original: string;
  corrigido: string;
  explicacao: string;
  severidade: Severidade;
};

function mapearCorrecoes(
  payload: components['schemas']['CorrectionPayload'][] | undefined,
): Correcao[] {
  return (payload ?? []).map((c) => ({
    index: c.index,
    tipo: c.type,
    original: c.original_excerpt,
    corrigido: c.corrected_form,
    explicacao: c.explanation,
    severidade: c.severity,
  }));
}

export type Turno = {
  estado: EstadoDoTurn;
  turnId: string | null;
  transcricao: string | null;
  /**
   * As correções do turn ATUAL — zeradas por `limpar()`, como o resto.
   *
   * Vazio cobre os dois casos "ainda não sei" e "não há nenhuma", e os dois
   * renderizam igual: nada (CARD-016, diagnóstico §5 — sem correção, sem
   * card, nem uma de afirmação positiva). Não há distinção a fazer.
   */
  correcoes: Correcao[];
  /**
   * A contagem por tipo desde que o app abriu (CARD-016 — fundação do resumo
   * completo da Fase 6). **Sobrevive a `limpar()`**: é da SESSÃO, não do
   * turn — zerar a cada gravação nova apagaria o que acabou de acontecer.
   */
  resumo: ResumoDaSessao;
  /** Os trechos conhecidos, em ordem de `index`. */
  trechos: Trecho[];
  /** Qual trecho está tocando agora. */
  tocando: number | null;
  /** Gaps medidos entre trechos, em ms. */
  gaps: number[];
  /**
   * Índices já tocados até o fim.
   *
   * Existe porque **"o turn completou" e "o aluno terminou de ouvir" são
   * instantes diferentes**: o `completed` chega enquanto o primeiro trecho ainda
   * toca. Quem mede gap precisa esperar o segundo.
   */
  tocados: number[];
  marcos: Marcos;
  erro: string | null;
  /**
   * Falhou **depois** de o aluno já ter ouvido algo (ADR-0023 item 6).
   * A UI diz o que aconteceu **sem apagar o que já foi ouvido**.
   */
  entregaParcial: boolean;
  /** Por onde os eventos chegaram — o recuo precisa ser visível. */
  via: 'sse' | 'polling' | null;
  /**
   * O áudio não pôde ser tocado, mas **o texto continua** (ADR-0024 item 5).
   * Nunca é tela de erro fatal.
   */
  audioIndisponivel: boolean;
  /**
   * A tela de exceção que cobre a conversa agora (CARD-027), ou `null` quando
   * nenhuma se aplica — o caminho comum. `estado` continua `'falhou'` nos
   * casos de cota/pausado/rede: `excecao` não é um estado NOVO da máquina, é
   * uma leitura adicional sobre o mesmo `'falhou'`, que decide qual overlay
   * (se algum) a tela mostra por cima do texto genérico.
   */
  excecao: ConteudoDeExcecao | null;
  /**
   * O botão `traduzir` (CARD-058). Igual a `correcoes`, some em `limpar()` —
   * gravar de novo ou trocar de tela descarta a tradução.
   */
  traducao: EstadoDeTraducao;
  /**
   * Pede a tradução da resposta do professor. **Não pede duas vezes** pela
   * mesma resposta (RNF6 do CARD-036): se já `traduzido` ou `traduzindo`,
   * reusa o que está em memória em vez de chamar o servidor de novo.
   */
  traduzir: () => Promise<void>;
  /** "Descartar" (CARD-032): chama o servidor e volta ao estado ocioso. */
  descartar: () => Promise<void>;
  /**
   * "Tentar enviar de novo" do artboard 14 (offline): reenvia a MESMA
   * gravação, com uma `Idempotency-Key` NOVA — a original nunca chegou ao
   * servidor (falha de transporte, não de aceite), então não há turn a
   * duplicar.
   */
  tentarNovamente: () => void;
  enviar: (uri: string, pararEm: number) => Promise<void>;
  limpar: () => void;
};

/**
 * Chave de idempotência: única, não secreta.
 *
 * Não usa `crypto.randomUUID` porque ele não é garantido no runtime do Hermes e
 * a alternativa seria `expo-crypto` — dependência nova para gerar um
 * identificador que só precisa não colidir consigo mesmo (ADR-0044, régua alta).
 */
function novaChave(): string {
  const aleatorio = Math.random().toString(36).slice(2, 12);
  return `turn-${Date.now().toString(36)}-${aleatorio}`;
}

/**
 * O tipo do arquivo, derivado da extensão — **não fixo**.
 *
 * O servidor tem uma lista fechada e responde **415** ao que não está nela
 * (`api/audio_intake.py`). `audio/m4a` **não** está: o nome aceito é
 * `audio/x-m4a`. Foi assim que este mapa nasceu — com um 415 de verdade, num
 * upload de verdade, e não lendo a lista.
 */
function descreverArquivo(uri: string): { nome: string; tipo: string } {
  const extensao = uri.split('.').pop()?.toLowerCase() ?? '';
  const tipos: Record<string, string> = {
    m4a: 'audio/x-m4a',
    mp4: 'audio/mp4',
    aac: 'audio/aac',
    wav: 'audio/wav',
    mp3: 'audio/mpeg',
    ogg: 'audio/ogg',
    opus: 'audio/opus',
    webm: 'audio/webm',
  };
  // O default é o que o `expo-audio` grava no iOS com `HIGH_QUALITY`.
  const tipo = tipos[extensao] ?? 'audio/x-m4a';
  const sufixo = extensao in tipos ? extensao : 'm4a';
  return { nome: `fala.${sufixo}`, tipo };
}

/** Backoff do polling, em ms. Termina em 2 s: o turn saudável fecha em ~3 s. */
const BACKOFF_POLLING = [300, 400, 600, 900, 1200, 2000];

function ordenarPorIndice(trechos: Trecho[]): Trecho[] {
  // Ordenação NUMÉRICA (ADR-0023 item 2). Comparação de string poria
  // `chunk:10` antes de `chunk:2`.
  return [...trechos].sort((a, b) => a.index - b.index);
}

export function useTurno(): Turno {
  const { fetchAutenticado } = useSessao();
  const cliente = useMemo<Cliente>(
    () => criarCliente({ baseUrl: config.apiBaseUrl, fetch: fetchAutenticado }),
    [fetchAutenticado],
  );
  const turnAtualRef = useRef<string | null>(null);
  /** Índices para os quais a recuperação já foi tentada — uma vez cada. */
  const jaRecuperados = useRef(new Set<number>());

  /**
   * Um trecho não carregou. **URL assinada expirada é o caso esperado**
   * (ADR-0024 item 3: o TTL é curto de propósito), e o ADR-0024 item 5 diz o
   * que fazer, em ordem: repedir o `GET` para reassinar; se o trecho já não
   * existir mas o `full` sim, tocar o inteiro; se nenhum dos dois, áudio
   * indisponível com o **texto preservado** — nunca uma tela de erro fatal.
   */
  const recuperarAudio = useCallback(
    async (index: number) => {
      const id = turnAtualRef.current;
      if (!id || jaRecuperados.current.has(index)) return;
      jaRecuperados.current.add(index);

      try {
        const turn = await cliente.obterTurn(id);
        // **A volta da rede é tarde demais para confiar no `id` de antes**
        // (CARD-042): entre o pedido e a resposta o aluno pode ter tocado em
        // gravar. `limpar()` zera `turnAtualRef`, e `enviar()` o troca pelo turn
        // novo — nos dois casos, renovar aqui faria o turn MORTO voltar a tocar.
        // O `abort()` não alcança isto: este `GET` é outra requisição.
        if (turnAtualRef.current !== id) return;
        const fresco = (turn.chunks ?? []).find((c) => c.index === index);
        if (fresco) {
          filaRef.current?.renovar(fresco);
          return;
        }
        if (turn.reply_audio_url) {
          filaRef.current?.tocarInteiro(turn.reply_audio_url);
          return;
        }
        setAudioIndisponivel(true);
      } catch {
        setAudioIndisponivel(true);
      }
    },
    [cliente],
  );

  const fila = useFilaDePlayback({ aoTravar: (i) => void recuperarAudio(i) });
  const filaRef = useRef(fila);
  filaRef.current = fila;

  const [estado, setEstado] = useState<EstadoDoTurn>('ocioso');
  const [turnId, setTurnId] = useState<string | null>(null);
  const [transcricao, setTranscricao] = useState<string | null>(null);
  const [correcoes, setCorrecoes] = useState<Correcao[]>([]);
  const [resumo, setResumo] = useState<ResumoDaSessao>(RESUMO_VAZIO);
  const [trechos, setTrechos] = useState<Trecho[]>([]);
  const [marcos, setMarcos] = useState<Marcos>(MARCOS_VAZIOS);
  const [erro, setErro] = useState<string | null>(null);
  const [entregaParcial, setEntregaParcial] = useState(false);
  const [via, setVia] = useState<'sse' | 'polling' | null>(null);
  const [audioIndisponivel, setAudioIndisponivel] = useState(false);
  const [excecao, setExcecao] = useState<ConteudoDeExcecao | null>(null);
  const [traducao, setTraducao] = useState<EstadoDeTraducao>(TRADUCAO_OCIOSA);
  /** Espelha `traducao` sem esperar o próximo render — mesmo padrão do `correcoesRef`. */
  const traducaoRef = useRef<EstadoDeTraducao>(TRADUCAO_OCIOSA);
  traducaoRef.current = traducao;

  const abortador = useRef<AbortController | null>(null);
  const sessaoId = useRef<string | null>(null);
  /** Ids de evento já processados — a dedup do ADR-0041 item 3. */
  const idsVistos = useRef(new Set<string>());
  const ultimoEventoId = useRef<string | null>(null);
  const encerrado = useRef(false);
  /** Espelha `correcoes` sem esperar o próximo render — mesmo padrão do `filaRef`. */
  const correcoesRef = useRef<Correcao[]>([]);
  correcoesRef.current = correcoes;
  /** `{ uri, pararEm }` da última gravação — o que "tentar de novo" reenvia. */
  const ultimaTentativa = useRef<{ uri: string; pararEm: number } | null>(null);
  /** O relógio do artboard 16: dispara "travado" se ninguém encerrar antes. */
  const travamentoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const desarmarTravamento = useCallback(() => {
    if (travamentoTimer.current !== null) {
      clearTimeout(travamentoTimer.current);
      travamentoTimer.current = null;
    }
  }, []);

  /**
   * Arma o watchdog do artboard 16 — "a resposta não chegou em 30s".
   *
   * Conta a partir do UPLOAD concluído (`turnId` já existe), como o texto do
   * artboard promete ("sua fala FOI ENVIADA, mas..."), não do início da
   * gravação. Ao disparar, só age se o turn ainda não tiver terminado —
   * `encerrado.current` é a MESMA flag que `aplicar`/`pollar` já mantêm, não
   * um relógio próprio que poderia dessincronizar dos dois.
   */
  const armarTravamento = useCallback(
    (id: string) => {
      desarmarTravamento();
      travamentoTimer.current = setTimeout(() => {
        if (!encerrado.current) {
          setExcecao(conteudoDoTravamento(id, config.respostaTravadaEmSegundos));
        }
      }, config.respostaTravadaEmSegundos * 1000);
    },
    [desarmarTravamento],
  );

  const cancelar = useCallback(() => {
    abortador.current?.abort();
    abortador.current = null;
  }, []);

  /**
   * Soma as correções do turn que acabou de fechar ao resumo da SESSÃO.
   *
   * Chamado uma vez por turn concluído (SSE ou polling), nunca por
   * `limpar()`: o resumo é a fundação do resumo pós-sessão da Fase 6, e
   * zerá-lo a cada gravação nova apagaria exatamente o que ele existe para
   * lembrar.
   */
  const registrarNoResumo = useCallback(() => {
    const atuais = correcoesRef.current;
    if (atuais.length === 0) return;
    setResumo((atual) => {
      const porTipo = { ...atual.porTipo };
      for (const c of atuais) porTipo[c.tipo] = (porTipo[c.tipo] ?? 0) + 1;
      return { total: atual.total + atuais.length, porTipo };
    });
  }, []);

  const limpar = useCallback(() => {
    cancelar();
    desarmarTravamento();
    fila.limpar();
    encerrado.current = false;
    idsVistos.current.clear();
    ultimoEventoId.current = null;
    turnAtualRef.current = null;
    setEstado('ocioso');
    setTurnId(null);
    setTranscricao(null);
    setCorrecoes([]);
    setTrechos([]);
    setMarcos(MARCOS_VAZIOS);
    setErro(null);
    setEntregaParcial(false);
    setVia(null);
    setAudioIndisponivel(false);
    setExcecao(null);
    setTraducao(TRADUCAO_OCIOSA);
    jaRecuperados.current.clear();
  }, [cancelar, desarmarTravamento, fila]);

  /**
   * O botão `traduzir` (CARD-058). Reusa o que já está em memória — pedir de
   * novo pela mesma resposta gastaria IA sem necessidade (RNF6 do CARD-036).
   * O alvo é sempre `reply`: o card cobre a resposta do professor, não as
   * correções (fora do escopo — ver "Out" do card).
   */
  const traduzir = useCallback(async () => {
    const id = turnAtualRef.current;
    if (!id) return;
    if (
      traducaoRef.current.fase === 'traduzido' ||
      traducaoRef.current.fase === 'traduzindo'
    ) {
      return;
    }
    setTraducao({ fase: 'traduzindo', texto: null });
    try {
      const resultado = await cliente.traduzirTexto(id, 'reply');
      setTraducao({ fase: 'traduzido', texto: resultado.text });
    } catch (falha) {
      console.error('[turno] traduzir falhou:', falha);
      setTraducao({ fase: 'falhou', texto: null });
    }
  }, [cliente]);

  const receberTrecho = useCallback(
    (trecho: Trecho) => {
      setMarcos((atual) =>
        atual.primeiroChunk === null ? { ...atual, primeiroChunk: Date.now() } : atual,
      );
      setTrechos((atual) =>
        atual.some((t) => t.index === trecho.index)
          ? atual
          : ordenarPorIndice([...atual, trecho]),
      );
      setEstado((atual) =>
        atual === 'concluido' || atual === 'falhou' ? atual : 'ouvindo',
      );
      // A fila descarta índice repetido por conta própria.
      fila.enfileirar(trecho);
    },
    [fila],
  );

  /** Aplica um evento do stream, ignorando o que já foi visto. */
  const aplicar = useCallback(
    (evento: EventoDoTurn) => {
      // **Dedup por id** (ADR-0041 item 3): o histórico da retomada e o canal ao
      // vivo podem entregar o mesmo evento. Sem isto, o aluno ouve a mesma frase
      // duas vezes — e o bug é intermitente.
      if (idsVistos.current.has(evento.id)) return;
      idsVistos.current.add(evento.id);
      ultimoEventoId.current = evento.id;

      switch (evento.tipo) {
        case 'transcribed':
          setTranscricao(evento.dados.transcript);
          setEstado((atual) => (atual === 'enviando' ? 'transcrevendo' : atual));
          break;
        case 'chunk':
          receberTrecho(evento.dados);
          break;
        case 'feedback':
          setCorrecoes(mapearCorrecoes(evento.dados.corrections));
          break;
        case 'completed':
          encerrado.current = true;
          desarmarTravamento();
          // A resposta chegou depois do watchdog do artboard 16 disparar — o
          // overlay "travado" não pode continuar cobrindo um turn que acabou
          // de terminar bem.
          setExcecao(null);
          setEstado('concluido');
          registrarNoResumo();
          break;
        case 'failed':
          encerrado.current = true;
          desarmarTravamento();
          setExcecao(null);
          // **Não apaga o que já foi ouvido** (ADR-0023 item 6).
          setEntregaParcial(evento.dados.delivered_partially);
          setErro(evento.dados.reason);
          setEstado('falhou');
          break;
      }
    },
    [receberTrecho, registrarNoResumo, desarmarTravamento],
  );

  /** O contrato de recuo: `GET /v1/turns/{id}` com backoff (ADR-0026 item 4). */
  const pollar = useCallback(
    async (id: string, sinal: AbortSignal) => {
      setVia('polling');
      for (let passo = 0; !sinal.aborted && !encerrado.current; passo++) {
        let turn: Turn;
        try {
          turn = await cliente.obterTurn(id, sinal);
        } catch (falha) {
          if (sinal.aborted) return;
          setErro(falha instanceof Error ? falha.message : String(falha));
          setEstado('falhou');
          return;
        }

        if (turn.transcript) setTranscricao(turn.transcript);
        for (const trecho of ordenarPorIndice(turn.chunks ?? [])) receberTrecho(trecho);
        // O recuo não tinha isto antes do CARD-016: `corrections` chega no
        // MESMO `GET` que já é chamado a cada passo, então não é uma
        // segunda chamada — é ler um campo que já estava na resposta. Antes
        // do professor fechar, `corrections` vem `[]` (é
        // `default_factory=list` no domínio, nunca ausente) — e vazio
        // renderiza igual a "nada ainda" ou "nada mesmo" (CARD-016): não há
        // distinção que a tela precise fazer.
        setCorrecoes(mapearCorrecoes(turn.corrections));

        if (turn.status === 'completed') {
          encerrado.current = true;
          desarmarTravamento();
          setExcecao(null);
          setEstado('concluido');
          registrarNoResumo();
          return;
        }
        if (turn.status === 'failed') {
          encerrado.current = true;
          desarmarTravamento();
          setExcecao(null);
          setEntregaParcial(turn.delivered_partially);
          setErro(turn.failure_reason ?? 'o turn falhou');
          setEstado('falhou');
          return;
        }

        const espera =
          BACKOFF_POLLING[Math.min(passo, BACKOFF_POLLING.length - 1)] ?? 2000;
        await new Promise((r) => setTimeout(r, espera));
      }
    },
    [cliente, receberTrecho, registrarNoResumo, desarmarTravamento],
  );

  /** O caminho principal: SSE, com queda para o polling se ele não se sustentar. */
  const acompanhar = useCallback(
    async (id: string, sinal: AbortSignal) => {
      if (!config.sseHabilitado) {
        await pollar(id, sinal);
        return;
      }

      try {
        setVia('sse');
        for await (const evento of cliente.acompanharTurn(id, {
          sinal,
          ultimoEventoId: ultimoEventoId.current,
        })) {
          if (sinal.aborted) return;
          aplicar(evento);
          if (encerrado.current) return;
        }
        // O stream fechou sem `completed`/`failed` — timeout do servidor ou
        // queda de rede. O turn continua vivo no banco; o recuo o termina.
        if (!sinal.aborted && !encerrado.current) await pollar(id, sinal);
      } catch (falha) {
        if (sinal.aborted) return;
        // **O recuo não é tratamento de exceção decorativo**: é o contrato.
        await pollar(id, sinal);
        if (encerrado.current) return;
        setErro(falha instanceof Error ? falha.message : String(falha));
      }
    },
    [cliente, aplicar, pollar],
  );

  const enviar = useCallback(
    async (uri: string, pararEm: number) => {
      // Guardado ANTES de `limpar()` — que não mexe nesta ref — para que
      // "tentar enviar de novo" (artboard 14) reenvie exatamente esta mesma
      // gravação mesmo depois de uma falha de rede zerar o resto do estado.
      ultimaTentativa.current = { uri, pararEm };
      limpar();
      // A chave nasce AQUI, uma vez. O retry, lá dentro, reusa esta mesma.
      const chave = novaChave();
      const controlador = new AbortController();
      abortador.current = controlador;

      setEstado('enviando');
      setMarcos({ ...MARCOS_VAZIOS, parouDeFalar: pararEm });
      await prepararParaTocar();

      try {
        if (!sessaoId.current) {
          const sessao = await cliente.criarSessao(controlador.signal);
          sessaoId.current = sessao.id;
        }

        const arquivo = descreverArquivo(uri);
        const bytes = await lerComoBlob(uri, arquivo.tipo);
        const aceito = await cliente.enviarTurn({
          sessionId: sessaoId.current,
          audio: bytes,
          nomeDoArquivo: arquivo.nome,
          idempotencyKey: chave,
          sinal: controlador.signal,
        });

        setMarcos((atual) => ({ ...atual, uploadCompleto: Date.now() }));
        setTurnId(aceito.turn_id);
        turnAtualRef.current = aceito.turn_id;
        setEstado('transcrevendo');
        // O relógio do artboard 16 começa AGORA — "sua fala FOI ENVIADA, mas
        // a resposta não chegou em 30s" — não no início da gravação.
        armarTravamento(aceito.turn_id);

        await acompanhar(aceito.turn_id, controlador.signal);
      } catch (falha) {
        if (controlador.signal.aborted) return;
        // `console.error` é permitido pelo Biome de propósito (ADR-0043): o
        // caminho triste tem de ser legível no log do Metro, ou depurar o app
        // vira leitura de captura de tela.
        console.error('[turno] falhou no envio:', falha);
        setErro(falha instanceof Error ? falha.message : String(falha));
        setEstado('falhou');
        // CARD-027: cota/kill switch/offline ganham tela própria por cima do
        // texto genérico acima — `conteudoDoErro` devolve `null` para
        // qualquer outro erro, e o texto genérico continua sendo a resposta.
        setExcecao(conteudoDoErro(falha));
      }
    },
    [cliente, limpar, acompanhar, armarTravamento],
  );

  /** "Descartar" (CARD-032): o servidor não apaga nada, só marca e some da tela. */
  const descartar = useCallback(async () => {
    const id = turnAtualRef.current;
    if (id) {
      try {
        await cliente.descartarTurn(id);
      } catch (falha) {
        // Mesmo padrão do resto do arquivo: o log é o instrumento, e o aluno
        // não fica preso esperando este `await` — o objetivo de "Descartar" é
        // destravar a tela, não confirmar com o servidor antes de deixar.
        console.error('[turno] descartar falhou:', falha);
      }
    }
    limpar();
  }, [cliente, limpar]);

  /** "Tentar enviar de novo" do artboard 14: reenvia a última gravação. */
  const tentarNovamente = useCallback(() => {
    const tentativa = ultimaTentativa.current;
    if (tentativa) void enviar(tentativa.uri, tentativa.pararEm);
  }, [enviar]);

  /**
   * O turn fechou: registra os quatro intervalos e os gaps no log.
   *
   * **Existe porque a tela de conversa não mostra marcos** — quem os exibe é a
   * rota `/medicao`, e ela usa um WAV fixo, não o microfone. Num aparelho
   * físico, medir a fala REAL exige que o número saia por algum lugar; sem
   * isto, o critério do CARD-037 depende de alguém cronometrar no olho.
   */
  useEffect(() => {
    if (estado !== 'concluido' && estado !== 'falhou') return;
    // Uma linha **por atualização de gap**, e não uma só: o `completed` chega
    // enquanto o primeiro trecho ainda toca, então a linha final de cada turn é
    // a última — que é a que tem os gaps completos. Tentei condicionar ao fim do
    // playback e o log parou de sair: quando o instrumento e a medição competem,
    // ganha o instrumento que registra demais, não o que registra de menos.
    const i = intervalos(marcos);
    console.info(
      `[turno] ${estado} · up ${i.upload}ms · chunk ${i.ateOChunk}ms · ` +
        `áudio ${i.ateOAudio}ms · TOTAL ${i.total}ms · ` +
        `${trechos.length} trechos · gaps [${fila.gaps.join(', ')}]`,
    );
  }, [estado, marcos, trechos.length, fila.gaps]);

  // O primeiro instante audível vem da fila; ele é o quarto marco.
  useEffect(() => {
    if (fila.primeiroAudivelEm === null) return;
    setMarcos((atual) =>
      atual.primeiroAudivel === null
        ? { ...atual, primeiroAudivel: fila.primeiroAudivelEm }
        : atual,
    );
  }, [fila.primeiroAudivelEm]);

  /**
   * Voltar do background reconecta a partir do último evento recebido.
   *
   * **`Last-Event-ID` fora do esquema é 400**, não "comece do começo" (ADR-0041
   * item 4) — por isso o valor é sempre o último id REAL, ou nenhum. O
   * `feedback` **já volta** na retomada desde o CARD-013 (`turn.corrections`
   * persistido tirou o motivo do ADR-0041 item 5 de existir) — mas nenhuma
   * tela pode depender dele para sair de um estado de espera: um turn sem
   * nenhuma correção nunca dispara esse evento de novo com conteúdo
   * observável diferente do que o `GET` de recuo já traz.
   */
  useEffect(() => {
    const aoMudar = (situacao: AppStateStatus) => {
      const id = turnAtualRef.current;
      if (situacao !== 'active' || !id || encerrado.current) return;
      cancelar();
      const controlador = new AbortController();
      abortador.current = controlador;
      void acompanhar(id, controlador.signal);
    };
    const inscricao = AppState.addEventListener('change', aoMudar);
    return () => inscricao.remove();
  }, [acompanhar, cancelar]);

  useEffect(() => cancelar, [cancelar]);
  useEffect(() => desarmarTravamento, [desarmarTravamento]);

  return {
    estado,
    turnId,
    transcricao,
    correcoes,
    resumo,
    trechos,
    tocando: fila.tocando,
    gaps: fila.gaps,
    tocados: fila.concluidos,
    marcos,
    erro,
    entregaParcial,
    via,
    audioIndisponivel,
    excecao,
    traducao,
    traduzir,
    descartar,
    tentarNovamente,
    enviar,
    limpar,
  };
}

export { intervalos };
