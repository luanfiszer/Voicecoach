/**
 * Redefinir senha com o código do e-mail. `?token=` pré-preenche o código —
 * para o dia em que o link do e-mail apontar para a web.
 */

import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { mensagemDeErro } from '@/features/auth/mensagensDeErro';
import { SENHA_MINIMA } from '@/features/auth/TelaCadastro';
import { useSessao } from '@/features/auth/useSessao';
import { Botao } from '@/ui/Botao';
import { Campo } from '@/ui/Campo';
import { LinkDeTexto } from '@/ui/LinkDeTexto';
import { PaginaDeFormulario } from '@/ui/PaginaDeFormulario';

export function TelaRedefinirSenha() {
  const sessao = useSessao();
  const navegar = useNavigate();
  const [parametros] = useSearchParams();
  const [codigo, setCodigo] = useState(parametros.get('token') ?? '');
  const [novaSenha, setNovaSenha] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [concluido, setConcluido] = useState(false);

  const valido = codigo.trim().length > 0 && novaSenha.length >= SENHA_MINIMA;

  const redefinir = async () => {
    if (!valido) return;
    setErro(null);
    setCarregando(true);
    try {
      await sessao.redefinirSenha(codigo.trim(), novaSenha);
      setConcluido(true);
    } catch (falha) {
      setErro(mensagemDeErro(falha));
    } finally {
      setCarregando(false);
    }
  };

  if (concluido) {
    return (
      <PaginaDeFormulario
        titulo="Senha redefinida"
        subtitulo="Por segurança, todas as suas sessões foram encerradas. Entre com a senha nova."
      >
        <Botao rotulo="Entrar" aoClicar={() => navegar('/entrar')} />
      </PaginaDeFormulario>
    );
  }

  return (
    <PaginaDeFormulario
      titulo="Redefinir senha"
      subtitulo="Cole aqui o código que veio no e-mail e escolha uma senha nova."
      aoEnviar={() => void redefinir()}
    >
      <Campo rotulo="Código do e-mail" valor={codigo} aoMudar={setCodigo} />
      <Campo
        rotulo="Nova senha"
        valor={novaSenha}
        aoMudar={setNovaSenha}
        tipo="password"
        autocompletar="new-password"
        erro={
          novaSenha.length > 0 && novaSenha.length < SENHA_MINIMA
            ? `Mínimo de ${SENHA_MINIMA} caracteres.`
            : null
        }
      />
      {erro ? <p className="erro">{erro}</p> : null}
      <Botao
        rotulo="Redefinir senha"
        tipo="submit"
        carregando={carregando}
        desabilitado={!valido}
      />
      <LinkDeTexto rotulo="Voltar para o login" aoClicar={() => navegar('/entrar')} />
    </PaginaDeFormulario>
  );
}
