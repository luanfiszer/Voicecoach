/**
 * `/confirmar-email?token=…` — a confirmação a partir do link (CARD-064).
 *
 * Hoje o link do e-mail aponta para a API (`GET /v1/auth/confirm-email`, que
 * responde JSON). Esta rota existe para o dia em que `PUBLIC_WEB_BASE_URL`
 * apontar o link para a web: o aluno cai numa página de verdade, não num JSON.
 * Funciona logado ou não.
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';

import { mensagemDeErro } from '@/features/auth/mensagensDeErro';
import { useSessao } from '@/features/auth/useSessao';
import { Botao } from '@/ui/Botao';
import { PaginaDeFormulario } from '@/ui/PaginaDeFormulario';

type Estado =
  | { tipo: 'confirmando' }
  | { tipo: 'ok' }
  | { tipo: 'falhou'; mensagem: string };

export function TelaConfirmarEmail() {
  const sessao = useSessao();
  const navegar = useNavigate();
  const [parametros] = useSearchParams();
  const token = parametros.get('token') ?? '';
  const [estado, setEstado] = useState<Estado>({ tipo: 'confirmando' });
  // O StrictMode monta duas vezes em desenvolvimento; o token é de uso único,
  // e a segunda chamada falharia por já ter sido consumido.
  const jaPediu = useRef(false);

  useEffect(() => {
    if (jaPediu.current) return;
    jaPediu.current = true;
    sessao
      .confirmarEmail(token)
      .then(() => setEstado({ tipo: 'ok' }))
      .catch((falha: unknown) =>
        setEstado({ tipo: 'falhou', mensagem: mensagemDeErro(falha) }),
      );
  }, [sessao, token]);

  const titulo =
    estado.tipo === 'ok'
      ? 'E-mail confirmado'
      : estado.tipo === 'falhou'
        ? 'Não deu para confirmar'
        : 'Confirmando…';

  return (
    <PaginaDeFormulario
      titulo={titulo}
      subtitulo={
        estado.tipo === 'ok'
          ? 'Pronto. Você já pode começar a falar.'
          : estado.tipo === 'falhou'
            ? estado.mensagem
            : null
      }
    >
      {estado.tipo !== 'confirmando' ? (
        <Botao rotulo="Continuar" aoClicar={() => navegar('/')} />
      ) : null}
    </PaginaDeFormulario>
  );
}
