/** "Confirme seu e-mail" — o aluno espera o link e pode pedir outro (CARD-050). */

import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';

import { mensagemDeErro } from '@/features/auth/mensagensDeErro';
import { useSessao } from '@/features/auth/useSessao';
import { Botao } from '@/ui/Botao';
import { LinkDeTexto } from '@/ui/LinkDeTexto';
import { PaginaDeFormulario } from '@/ui/PaginaDeFormulario';

export function TelaConfirmeSeuEmail() {
  const sessao = useSessao();
  const navegar = useNavigate();
  const [parametros] = useSearchParams();
  const email = parametros.get('email') ?? '';
  const [carregando, setCarregando] = useState(false);
  const [mensagem, setMensagem] = useState<string | null>(null);

  const reenviar = async () => {
    setCarregando(true);
    setMensagem(null);
    try {
      await sessao.reenviarConfirmacao(email);
      setMensagem('Link reenviado. Confira sua caixa de entrada.');
    } catch (falha) {
      setMensagem(mensagemDeErro(falha));
    } finally {
      setCarregando(false);
    }
  };

  return (
    <PaginaDeFormulario
      titulo="Confirme seu e-mail"
      subtitulo={
        <>
          Enviamos um link de confirmação para <strong>{email}</strong>. Clique nele
          para poder começar a falar.
        </>
      }
    >
      {mensagem ? <p className="apoio">{mensagem}</p> : null}
      <Botao
        rotulo="Reenviar e-mail"
        aoClicar={() => void reenviar()}
        carregando={carregando}
        desabilitado={email.length === 0}
      />
      <LinkDeTexto rotulo="Voltar para o login" aoClicar={() => navegar('/entrar')} />
    </PaginaDeFormulario>
  );
}
