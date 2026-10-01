/**
 * As rotas da web (CARD-064). Na web, ao contrário do mobile, as telas de
 * auth têm URL própria: o botão Voltar do navegador precisa funcionar, e os
 * links de e-mail (confirmar, redefinir) precisam cair numa página.
 *
 * **Quem decide o que aparece é o estado da sessão**, não a rota pedida:
 * deslogado em rota logada vai para `/entrar`; logado em rota de auth vai
 * para o histórico. `/confirmar-email` funciona nos dois estados.
 */

import { Navigate, Outlet, Route, Routes } from 'react-router';

import { TelaCadastro } from '@/features/auth/TelaCadastro';
import { TelaConfirmarEmail } from '@/features/auth/TelaConfirmarEmail';
import { TelaConfirmeSeuEmail } from '@/features/auth/TelaConfirmeSeuEmail';
import { TelaEntrada } from '@/features/auth/TelaEntrada';
import { TelaEsqueciASenha } from '@/features/auth/TelaEsqueciASenha';
import { TelaRedefinirSenha } from '@/features/auth/TelaRedefinirSenha';
import { useSessao } from '@/features/auth/useSessao';
import { Casca, TelaDeCarregamento } from '@/features/casca/Casca';
import { TelaConfiguracoes } from '@/features/configuracoes/TelaConfiguracoes';
import { TelaConta } from '@/features/conta/TelaConta';
import { TelaConversa } from '@/features/conversa/TelaConversa';
import { TelaHistorico } from '@/features/historico/TelaHistorico';

function SoDeslogado() {
  const { estado } = useSessao();
  if (estado === 'carregando') return <TelaDeCarregamento />;
  if (estado === 'autenticado') return <Navigate to="/historico" replace />;
  return <Outlet />;
}

function SoLogado() {
  const { estado } = useSessao();
  if (estado === 'carregando') return <TelaDeCarregamento />;
  if (estado === 'nao_autenticado') return <Navigate to="/entrar" replace />;
  return <Outlet />;
}

export function App() {
  return (
    <Routes>
      <Route element={<SoDeslogado />}>
        <Route path="/entrar" element={<TelaEntrada />} />
        <Route path="/criar-conta" element={<TelaCadastro />} />
        <Route path="/confirme-seu-email" element={<TelaConfirmeSeuEmail />} />
        <Route path="/esqueci-a-senha" element={<TelaEsqueciASenha />} />
        <Route path="/redefinir-senha" element={<TelaRedefinirSenha />} />
      </Route>

      <Route path="/confirmar-email" element={<TelaConfirmarEmail />} />

      <Route element={<SoLogado />}>
        <Route element={<Casca />}>
          <Route path="/conversa" element={<TelaConversa />} />
          <Route path="/historico" element={<TelaHistorico />} />
          <Route path="/conta" element={<TelaConta />} />
          <Route path="/configuracoes" element={<TelaConfiguracoes />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/historico" replace />} />
    </Routes>
  );
}
