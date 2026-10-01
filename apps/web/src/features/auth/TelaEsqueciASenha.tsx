/**
 * "Esqueci minha senha" — a resposta é sempre a mesma, com conta ou sem
 * (CARD-049: não vazar quais e-mails existem).
 */

import { useState } from 'react';
import { useNavigate } from 'react-router';

import { mensagemDeErro } from '@/features/auth/mensagensDeErro';
import { useSessao } from '@/features/auth/useSessao';
import { Botao } from '@/ui/Botao';
import { Campo } from '@/ui/Campo';
import { LinkDeTexto } from '@/ui/LinkDeTexto';
import { PaginaDeFormulario } from '@/ui/PaginaDeFormulario';

export function TelaEsqueciASenha() {
  const sessao = useSessao();
  const navegar = useNavigate();
  const [email, setEmail] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const pedir = async () => {
    if (email.trim().length === 0) return;
    setErro(null);
    setCarregando(true);
    try {
      await sessao.pedirRedefinicaoDeSenha(email.trim());
      setEnviado(true);
    } catch (falha) {
      setErro(mensagemDeErro(falha));
    } finally {
      setCarregando(false);
    }
  };

  return (
    <PaginaDeFormulario
      titulo="Esqueceu sua senha?"
      subtitulo="Informe seu e-mail. Se ele tiver conta, enviamos um link para redefinir a senha."
      aoEnviar={() => void pedir()}
    >
      <Campo
        rotulo="E-mail"
        valor={email}
        aoMudar={setEmail}
        tipo="email"
        autocompletar="email"
      />
      {erro ? <p className="erro">{erro}</p> : null}
      {enviado ? (
        <p className="apoio">
          Se esse e-mail tiver conta, o link chegou. Volte aqui com o código assim que o
          tiver.
        </p>
      ) : null}
      <Botao
        rotulo="Enviar link"
        tipo="submit"
        carregando={carregando}
        desabilitado={email.trim().length === 0}
      />
      <LinkDeTexto
        rotulo="Já tenho o código"
        aoClicar={() => navegar('/redefinir-senha')}
      />
      <LinkDeTexto rotulo="Voltar para o login" aoClicar={() => navegar('/entrar')} />
    </PaginaDeFormulario>
  );
}
