/**
 * Entrar — o `TelaEntrada` do mobile (CARD-050/060), na web.
 *
 * Sucesso não navega: o estado da sessão muda para `autenticado` e o roteador
 * (`App.tsx`) troca de tela sozinho — o mesmo desenho do mobile.
 */

import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router';

import { config } from '@/config';
import { BotaoGoogle } from '@/features/auth/BotaoGoogle';
import { mensagemDeErro } from '@/features/auth/mensagensDeErro';
import { useSessao } from '@/features/auth/useSessao';
import { Botao } from '@/ui/Botao';
import { Campo } from '@/ui/Campo';
import { LinkDeTexto } from '@/ui/LinkDeTexto';
import { PaginaDeFormulario } from '@/ui/PaginaDeFormulario';
import estilos from '@/ui/ui.module.css';

export function TelaEntrada() {
  const sessao = useSessao();
  const navegar = useNavigate();
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const entrar = async () => {
    if (email.trim().length === 0 || senha.length === 0) return;
    setErro(null);
    setCarregando(true);
    try {
      await sessao.login(email.trim(), senha);
    } catch (falha) {
      setErro(mensagemDeErro(falha));
      setCarregando(false);
    }
  };

  const entrarComGoogle = useCallback(
    async (idToken: string) => {
      setErro(null);
      try {
        await sessao.loginGoogle(idToken);
      } catch (falha) {
        setErro(mensagemDeErro(falha));
      }
    },
    [sessao],
  );

  return (
    <PaginaDeFormulario
      titulo="Bem-vindo de volta"
      subtitulo="Entre para continuar de onde parou."
      aoEnviar={() => void entrar()}
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
        autocompletar="current-password"
      />

      {erro ? <p className="erro">{erro}</p> : null}

      <Botao
        rotulo="Entrar"
        tipo="submit"
        carregando={carregando}
        desabilitado={email.trim().length === 0 || senha.length === 0}
      />

      <LinkDeTexto
        rotulo="Esqueci minha senha"
        aoClicar={() => navegar('/esqueci-a-senha')}
      />

      {config.googleClientId ? (
        <>
          <div className={estilos.separador}>ou</div>
          <BotaoGoogle
            clientId={config.googleClientId}
            aoReceberIdToken={(idToken) => void entrarComGoogle(idToken)}
            aoFalhar={setErro}
          />
        </>
      ) : null}

      <div className={estilos.rodape}>
        <span className="apoio">Não tem conta?</span>
        <LinkDeTexto rotulo="Criar conta" aoClicar={() => navegar('/criar-conta')} />
      </div>
    </PaginaDeFormulario>
  );
}
