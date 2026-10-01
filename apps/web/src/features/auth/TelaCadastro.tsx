/**
 * Criar conta — o `TelaCadastro` do mobile. Sucesso NÃO loga: o servidor exige
 * e-mail confirmado antes do primeiro turn (ADR-0007), então o próximo passo
 * é a tela "confirme seu e-mail".
 */

import { useState } from 'react';
import { useNavigate } from 'react-router';

import { mensagemDeErro } from '@/features/auth/mensagensDeErro';
import { useSessao } from '@/features/auth/useSessao';
import { Botao } from '@/ui/Botao';
import { Campo } from '@/ui/Campo';
import { LinkDeTexto } from '@/ui/LinkDeTexto';
import { PaginaDeFormulario } from '@/ui/PaginaDeFormulario';
import estilos from '@/ui/ui.module.css';

// O mesmo piso do servidor (`RegisterRequest`, CARD-049).
export const SENHA_MINIMA = 8;

export function TelaCadastro() {
  const sessao = useSessao();
  const navegar = useNavigate();
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const valido = email.trim().length > 0 && senha.length >= SENHA_MINIMA;

  const registrar = async () => {
    if (!valido) return;
    setErro(null);
    setCarregando(true);
    try {
      await sessao.registrar(email.trim(), senha);
      navegar(`/confirme-seu-email?email=${encodeURIComponent(email.trim())}`);
    } catch (falha) {
      setErro(mensagemDeErro(falha));
      setCarregando(false);
    }
  };

  return (
    <PaginaDeFormulario
      titulo="Seu tutor de inglês por conversa."
      subtitulo="Crie sua conta para começar a falar."
      aoEnviar={() => void registrar()}
    >
      <Campo
        rotulo="E-mail"
        valor={email}
        aoMudar={setEmail}
        tipo="email"
        autocompletar="email"
      />
      <Campo
        rotulo="Senha"
        valor={senha}
        aoMudar={setSenha}
        tipo="password"
        autocompletar="new-password"
        erro={
          senha.length > 0 && senha.length < SENHA_MINIMA
            ? `Mínimo de ${SENHA_MINIMA} caracteres.`
            : null
        }
      />

      {erro ? <p className="erro">{erro}</p> : null}

      <Botao
        rotulo="Criar conta"
        tipo="submit"
        carregando={carregando}
        desabilitado={!valido}
      />

      <div className={estilos.rodape}>
        <span className="apoio">Já tem conta?</span>
        <LinkDeTexto rotulo="Entrar" aoClicar={() => navegar('/entrar')} />
      </div>
    </PaginaDeFormulario>
  );
}
